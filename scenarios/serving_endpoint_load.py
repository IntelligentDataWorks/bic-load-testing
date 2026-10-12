"""Sustained-load variant of the serving-endpoint smoke test.

Same request/response contract as serving_endpoint_smoke.py (MLflow
ResponsesAgent: {"input": [...], "custom_inputs": {...}} in, {"output": [...]}
out) and the same BIC_AUTH_TOKEN / BIC_TEST_USER_ID requirements -- the only
difference is that a virtual user keeps issuing invocations for the configured
run time instead of stopping after one, so the endpoint can be measured under
concurrency:

    locust --config config/locust.serving-stress.conf

This bypasses React and the FastAPI BFF entirely. It still exercises the agent
orchestrator and everything downstream of it (Genie/SQL, model serving), so a
failure here is an agent-or-below problem, not a UI or BFF problem.

Every virtual user shares the one BIC_AUTH_TOKEN, so this is concurrency under
a *single* Databricks identity -- it does not exercise per-user isolation or
per-user rate limits.

Optional question catalogue (used by config/locust.prod-serving-*.conf):

  BIC_QUESTIONS_FILE  id|domain|kind|question file (e.g. data/prod_questions.txt).
                      When set, one cycle shared by all virtual users hands out the
                      next question instead of BIC_TEST_QUESTION, and each request
                      is named "<endpoint> [<domain>]" so latency splits per domain.
  BIC_RESULTS_JSONL   when set, one sanitized JSON line per invocation (question id,
                      expected vs routed domain, orchestrator action, status, latency).
                      Never contains the token.
"""

import itertools
import json
import os
import threading
import time
import uuid
from pathlib import Path

from locust import between, task

from auth import TokenAuthHttpUser

DEFAULT_ENDPOINT_PATH = "/serving-endpoints/ds-insights-companion-agent-dev/invocations"
DEFAULT_RESPONSE_TIMEOUT_SECONDS = 180
DEFAULT_QUESTION = "Hello"
DEFAULT_SESSION_ID_PREFIX = "load_test"

ENDPOINT_PATH = os.getenv("BIC_SERVING_ENDPOINT_PATH", DEFAULT_ENDPOINT_PATH)
RESPONSE_TIMEOUT_SECONDS = int(
    os.getenv("BIC_REQUEST_TIMEOUT_SECONDS", str(DEFAULT_RESPONSE_TIMEOUT_SECONDS))
)
RESULTS_JSONL = os.getenv("BIC_RESULTS_JSONL")
_results_lock = threading.Lock()


def _load_questions():
    path = os.getenv("BIC_QUESTIONS_FILE")
    if not path:
        return None
    from chat_outcome import load_questions

    questions = load_questions(Path(path))
    if not questions:
        raise ValueError(f"BIC_QUESTIONS_FILE {path} has no questions")
    return itertools.cycle(questions)


_next_question = _load_questions()


def _orchestrator_payload(body: dict) -> dict:
    """The agent returns its orchestrator result as JSON inside the first output_text."""
    for item in body.get("output") or []:
        for part in item.get("content") or [] if isinstance(item, dict) else []:
            if isinstance(part, dict) and part.get("type") == "output_text":
                try:
                    parsed = json.loads(part.get("text") or "")
                except ValueError:
                    return {}
                return parsed if isinstance(parsed, dict) else {}
    return {}


def _record(row: dict) -> None:
    if not RESULTS_JSONL:
        return
    with _results_lock, open(RESULTS_JSONL, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _has_agent_error(body: dict) -> bool:
    if body.get("error"):
        return True
    output = body.get("output") or []
    return any(isinstance(item, dict) and item.get("type") == "error" for item in output)


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"{name} must be set to run the serving-endpoint load test")
    return value


class ServingEndpointLoadUser(TokenAuthHttpUser):
    """Repeatedly invokes the serving endpoint for the duration of the run."""

    wait_time = between(1, 3)

    def on_start(self):
        super().on_start()
        # Fail loudly rather than silently sending unauthenticated requests.
        _require_env("BIC_AUTH_TOKEN")
        self.user_id = _require_env("BIC_TEST_USER_ID")

    @task
    def invoke(self):
        prefix = os.getenv("BIC_SESSION_ID_PREFIX", DEFAULT_SESSION_ID_PREFIX)
        # A fresh session id per invocation keeps virtual users from sharing
        # conversation state on the agent side.
        session_id = f"{prefix}_{uuid.uuid4().hex}"
        q = next(_next_question) if _next_question else None
        question = q.text if q else os.getenv("BIC_TEST_QUESTION", DEFAULT_QUESTION)
        name = f"{ENDPOINT_PATH} [{q.domain}]" if q else ENDPOINT_PATH
        payload = {
            "input": [{"role": "user", "content": question}],
            "custom_inputs": {"session_id": session_id, "user_id": self.user_id},
        }
        row = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "question_id": q.id if q else None,
            "expected_domain": q.domain if q else None,
            "kind": q.kind if q else None,
            "session_id": session_id,
        }
        started = time.perf_counter()

        with self.client.post(
            ENDPOINT_PATH,
            json=payload,
            name=name,
            timeout=RESPONSE_TIMEOUT_SECONDS,
            catch_response=True,
        ) as resp:
            row["status"] = resp.status_code
            row["latency_s"] = round(time.perf_counter() - started, 2)
            verdict = self._verdict(resp, row)
            row["verdict"] = verdict or "ok"
            if verdict:
                resp.failure(verdict)
            else:
                resp.success()
        _record(row)

    def _verdict(self, resp, row: dict):
        """Return a failure reason, or None when the invocation succeeded."""
        if resp.status_code != 200:
            # Never log the token -- only status/body-shape details.
            hint = (
                " -- BIC_AUTH_TOKEN is likely missing/expired"
                if resp.status_code == 401
                else ""
            )
            row["error_snippet"] = (resp.text or "")[:300]
            return f"unexpected status {resp.status_code}{hint}"
        try:
            body = resp.json()
        except ValueError:
            return "response was not valid JSON"
        if not body.get("output"):
            return "response had no non-empty 'output'"
        if _has_agent_error(body):
            return "agent response contained an error"
        orchestrator = _orchestrator_payload(body)
        row["action"] = orchestrator.get("action")
        row["routed_domain"] = orchestrator.get("domain")
        answer = orchestrator.get("response") or orchestrator.get("message")
        row["answer_snippet"] = json.dumps(answer, ensure_ascii=False)[:300]
        if orchestrator.get("action") == "error":
            return "orchestrator action=error"
        return None

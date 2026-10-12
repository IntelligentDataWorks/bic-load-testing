"""BicApiUser models the DS Insights Companion BFF's documented request flow.

Endpoints and response shapes below are taken from the BFF's own openapi.json
(operationIds / component schemas), not guessed:

  1. GET  /api/health         -> HealthResponse {status, contract_version, app_env}
  2. GET  /api/healthz        -> HealthzResponse {ok, who, auth_mode}
  3. GET  /api/me             -> MeResponse {email, name, user_id, authenticated, auth_mode}
  4. GET  /api/data-sources   -> DataSourcesResponse {environment, sources[]}
  5. GET  /api/sessions       -> sessions owned by the caller (loose shape per spec)
  6. create/obtain a session  -> BFF has no dedicated endpoint; a session_id is
                                  minted client-side and adopted on first /api/chat call
  7. POST /api/chat           -> ChatResult {session_id, user_query_id, action, ...}
  8. GET  /api/session-chat   -> chat history for that session
  9. POST /api/visualization  -> VisualizationResponse, only when the chat turn's
                                  text2sql.sql_data actually has rows to plot

POST /api/chat/stream is deliberately not modeled here: see stream_scenario.py,
since SSE timing needs to be measured differently from normal request/response calls.
/api/schema, /api/table/sort, /api/query-feedback, /api/query-metrics and
/api/historical-query are not yet modeled.

Steps 6-9 (the stateful chat flow) are gated behind ENABLE_FULL_FLOW, on by
default, so the demo run exercises the whole sequence; set
BIC_ENABLE_FULL_FLOW=false to fall back to read-only checks only.

Auth (see auth.py) is a shared BIC_AUTH_TOKEN bearer header, populated from a
Databricks OAuth U2M token for deployed/authenticated runs and left unset for
local, unauthenticated runs against FastAPI directly.
"""

import os
import random
import uuid
from pathlib import Path

from locust import SequentialTaskSet, between, task

from auth import TokenAuthHttpUser
from chat_outcome import classify_chat_result

ENABLE_FULL_FLOW = os.getenv("BIC_ENABLE_FULL_FLOW", "true").lower() == "true"

AUTH_MODES = {"obo", "pat_fallback"}
CHAT_ACTIONS = {"summarized", "clarification_needed", "return_response", "error"}
DEFAULT_QUESTIONS = ["What were last week's top selling products?"]
SAMPLE_QUESTIONS_FILE = Path(__file__).resolve().parent.parent / "data" / "sample_questions.txt"


def _load_sample_questions() -> list:
    if SAMPLE_QUESTIONS_FILE.exists():
        lines = SAMPLE_QUESTIONS_FILE.read_text(encoding="utf-8").splitlines()
        questions = [ln.strip() for ln in lines if ln.strip() and not ln.strip().startswith("#")]
        if questions:
            return questions
    return DEFAULT_QUESTIONS


SAMPLE_QUESTIONS = _load_sample_questions()


def _is_valid_health(body: dict) -> bool:
    return (
        body.get("status") == "ok"
        and isinstance(body.get("contract_version"), str)
        and isinstance(body.get("app_env"), str)
    )


def _is_valid_healthz(body: dict) -> bool:
    return (
        isinstance(body.get("ok"), bool)
        and isinstance(body.get("who"), str)
        and body.get("auth_mode") in AUTH_MODES
    )


def _is_valid_me(body: dict) -> bool:
    return (
        isinstance(body.get("email"), str)
        and isinstance(body.get("name"), str)
        and isinstance(body.get("user_id"), str)
        and isinstance(body.get("authenticated"), bool)
        and body.get("auth_mode") in AUTH_MODES
    )


def _is_valid_data_sources(body: dict) -> bool:
    if not isinstance(body.get("environment"), str):
        return False
    sources = body.get("sources", [])
    if not isinstance(sources, list):
        return False
    return all(isinstance(s, dict) and {"id", "name", "description"} <= s.keys() for s in sources)


def _is_valid_sessions(body) -> bool:
    # /api/sessions is `additionalProperties: true` in the spec -- no fixed shape to check beyond "is an object".
    return isinstance(body, dict)


def _is_valid_chat_result(body: dict) -> bool:
    return (
        isinstance(body.get("session_id"), str)
        and isinstance(body.get("user_query_id"), str)
        and body.get("action") in CHAT_ACTIONS
    )


def _is_valid_visualization(body: dict) -> bool:
    required = {
        "chart_type", "x_col", "y_col", "title",
        "columns", "numeric_columns", "rows", "x_label", "y_label",
    }
    return isinstance(body, dict) and required <= body.keys()


class BicApiFlow(SequentialTaskSet):
    """Ordered walk through the BFF contract; one pass per virtual user loop."""

    def on_start(self):
        self.session_id = None
        self.last_chat_result = None

    @task
    def check_health(self):
        with self.client.get("/api/health", name="/api/health", catch_response=True) as resp:
            if resp.status_code != 200:
                resp.failure(f"unexpected status {resp.status_code}")
                return
            try:
                body = resp.json()
            except ValueError:
                resp.failure("response was not valid JSON")
                return
            if not _is_valid_health(body):
                resp.failure(f"response shape did not match HealthResponse: {body}")
                return
            resp.success()

    @task
    def check_healthz(self):
        with self.client.get("/api/healthz", name="/api/healthz", catch_response=True) as resp:
            if resp.status_code != 200:
                resp.failure(f"unexpected status {resp.status_code}")
                return
            try:
                body = resp.json()
            except ValueError:
                resp.failure("response was not valid JSON")
                return
            if not _is_valid_healthz(body):
                resp.failure(f"response shape did not match HealthzResponse: {body}")
                return
            resp.success()

    @task
    def check_me(self):
        with self.client.get("/api/me", name="/api/me", catch_response=True) as resp:
            if resp.status_code != 200:
                resp.failure(f"unexpected status {resp.status_code}")
                return
            try:
                body = resp.json()
            except ValueError:
                resp.failure("response was not valid JSON")
                return
            if not _is_valid_me(body):
                resp.failure(f"response shape did not match MeResponse: {body}")
                return
            resp.success()

    @task
    def list_data_sources(self):
        with self.client.get("/api/data-sources", name="/api/data-sources", catch_response=True) as resp:
            if resp.status_code != 200:
                resp.failure(f"unexpected status {resp.status_code}")
                return
            try:
                body = resp.json()
            except ValueError:
                resp.failure("response was not valid JSON")
                return
            if not _is_valid_data_sources(body):
                resp.failure(f"response shape did not match DataSourcesResponse: {body}")
                return
            resp.success()

    @task
    def list_sessions(self):
        if not ENABLE_FULL_FLOW:
            return
        with self.client.get("/api/sessions", name="/api/sessions", catch_response=True) as resp:
            if resp.status_code != 200:
                resp.failure(f"unexpected status {resp.status_code}")
                return
            try:
                body = resp.json()
            except ValueError:
                resp.failure("response was not valid JSON")
                return
            if not _is_valid_sessions(body):
                resp.failure(f"response shape did not match expected sessions object: {body}")
                return
            resp.success()

    @task
    def create_or_obtain_session(self):
        if not ENABLE_FULL_FLOW:
            return
        self.session_id = self.session_id or str(uuid.uuid4())

    @task
    def submit_chat_question(self):
        if not ENABLE_FULL_FLOW:
            return
        payload = {"query": random.choice(SAMPLE_QUESTIONS), "session_id": self.session_id}
        with self.client.post("/api/chat", json=payload, name="/api/chat", catch_response=True) as resp:
            if resp.status_code != 200:
                resp.failure(f"unexpected status {resp.status_code}")
                return
            try:
                body = resp.json()
            except ValueError:
                resp.failure("response was not valid JSON")
                return
            if not _is_valid_chat_result(body):
                resp.failure(f"response shape did not match ChatResult: {body}")
                return
            self.session_id = body["session_id"]
            self.last_chat_result = body
            # HTTP 200 is not an answer: see chat_outcome.py for the business verdict.
            outcome = classify_chat_result(body)
            if outcome.verdict == "incomplete":
                # Clarifications get their own stats row so they neither pass as
                # answers nor dilute the answer latency.
                resp.request_meta["name"] = f"/api/chat [{outcome.classification}]"
                resp.success()
            elif outcome.verdict == "failed":
                resp.failure(f"{outcome.classification}: {outcome.reason}")
            else:
                resp.success()

    @task
    def read_chat_history(self):
        if not ENABLE_FULL_FLOW or not self.session_id:
            return
        params = {"session_id": self.session_id}
        with self.client.get(
            "/api/session-chat", params=params, name="/api/session-chat", catch_response=True
        ) as resp:
            if resp.status_code != 200:
                resp.failure(f"unexpected status {resp.status_code}")
                return
            try:
                resp.json()
            except ValueError:
                resp.failure("response was not valid JSON")
                return
            resp.success()

    @task
    def request_visualization(self):
        if not ENABLE_FULL_FLOW or not self.last_chat_result:
            return
        text2sql = self.last_chat_result.get("text2sql") or {}
        rows = text2sql.get("sql_data") or []
        # Only chart when the chat turn actually returned tabular data to plot.
        if not rows:
            return
        payload = {"rows": rows, "chart_type": "bar"}
        with self.client.post(
            "/api/visualization", json=payload, name="/api/visualization", catch_response=True
        ) as resp:
            if resp.status_code != 200:
                resp.failure(f"unexpected status {resp.status_code}")
                return
            try:
                body = resp.json()
            except ValueError:
                resp.failure("response was not valid JSON")
                return
            if not _is_valid_visualization(body):
                resp.failure(f"response shape did not match VisualizationResponse: {body}")
                return
            resp.success()


class BicApiUser(TokenAuthHttpUser):
    """Virtual user exercising the DS Insights Companion BFF per openapi.json."""

    tasks = [BicApiFlow]
    wait_time = between(1, 3)

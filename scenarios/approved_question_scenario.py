"""ApprovedQuestionUser: BFF chat load driven by the approved question catalogue.

Each loop is one business journey:

  1. POST /api/chat           one approved question in a new, test-owned session
  2. GET  /api/session-chat   read the session back: one record, this question

Questions come from data/approved_questions.txt in a fixed order. A single cycle
shared by all virtual users hands out the next question, so 1, 5 and 10 users run
the same question distribution and only the concurrency changes.

  BIC_WORKLOAD_IDS   comma-separated question IDs, in the order to cycle through
                     (repeat an ID to weight it). Default: every question in the file.
  BIC_CHAT_TIMEOUT_S client timeout for /api/chat (default 330: the BFF gives the
                     agent 300 s before it returns 504)

Verdicts use chat_outcome.py, not the HTTP status:

  completed  (FULL_ANSWER, VALID_DIRECT_RESPONSE)  -> "/api/chat" success
  failed     (refusal, error, empty, timeout, ...)   -> "/api/chat" failure
  incomplete (CLARIFICATION, PARTIAL_ANSWER)        -> "/api/chat [CLARIFICATION]" etc.,
                                                       success, so it is counted on its
                                                       own row and not in the answer latency

The sanitized outcome record (chat_outcome.ChatOutcome.to_record) is attached to
the request event's context under "chat_outcome" for any listener that audits it.
Each journey uses a new session owned by one virtual user; sessions are never shared.
"""

import itertools
import os
import uuid
from pathlib import Path

from locust import between, task

import chat_outcome as co
from auth import TokenAuthHttpUser

QUESTIONS_FILE = Path(__file__).resolve().parent.parent / "data" / "approved_questions.txt"
CHAT_TIMEOUT_S = float(os.getenv("BIC_CHAT_TIMEOUT_S", "330"))


def _workload() -> list:
    questions = {q.id: q for q in co.load_questions(QUESTIONS_FILE)}
    ids = [i.strip() for i in os.getenv("BIC_WORKLOAD_IDS", "").split(",") if i.strip()]
    unknown = [i for i in ids if i not in questions]
    if unknown:
        raise ValueError(f"BIC_WORKLOAD_IDS has unknown question ids: {unknown}")
    return [questions[i] for i in ids] if ids else list(questions.values())


WORKLOAD = _workload()
_next_question = itertools.cycle(WORKLOAD)


class ApprovedQuestionUser(TokenAuthHttpUser):
    wait_time = between(1, 3)

    @task
    def journey(self):
        question = next(_next_question)
        session_id = f"lt-{uuid.uuid4().hex}"
        payload = {"query": question.text, "session_id": session_id}
        context = {"question_id": question.id, "domain": question.domain, "session_id": session_id}
        with self.client.post(
            "/api/chat",
            json=payload,
            name="/api/chat",
            context=context,
            timeout=CHAT_TIMEOUT_S,
            catch_response=True,
        ) as resp:
            timed_out = resp.status_code == 0 and "Timeout" in type(resp.error).__name__
            outcome = co.classify_http_response(
                resp.status_code or None,
                resp.text,
                timed_out=timed_out,
                kind=question.kind,
                subjects=question.subjects,
            )
            record = outcome.to_record()
            record["session_echo_ok"] = outcome.session_id == session_id if outcome.session_id else None
            resp.request_meta["context"]["chat_outcome"] = record
            if outcome.verdict == "incomplete":
                resp.request_meta["name"] = f"/api/chat [{outcome.classification}]"
                resp.success()
            elif outcome.verdict == "failed":
                resp.failure(f"{outcome.classification}: {outcome.reason}")
            elif record["session_echo_ok"] is False:
                resp.failure("session echo mismatch")
            else:
                resp.success()
        if outcome.http_status != 200:
            return

        with self.client.get(
            "/api/session-chat",
            params={"session_id": session_id},
            name="/api/session-chat",
            context={"question_id": question.id, "session_id": session_id},
            catch_response=True,
        ) as resp:
            if resp.status_code != 200:
                resp.failure(f"unexpected status {resp.status_code}")
                return
            try:
                body = resp.json()
            except ValueError:
                resp.failure("response was not valid JSON")
                return
            chats = body.get("chats") or []
            isolated = (
                body.get("session_id") == session_id
                and len(chats) == 1
                and (chats[0].get("user_query") or "").strip() == question.text.strip()
            )
            resp.request_meta["context"]["history_isolated"] = isolated
            if not isolated:
                resp.failure(f"session history mismatch: count={body.get('count')}")
                return
            resp.success()

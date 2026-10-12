"""Business-outcome classification for one BFF chat turn.

HTTP 200 only says the BFF answered. Whether the user got an answer is in the
ChatResult body, whose ``action`` discriminator is documented in openapi.json and
set by ``to_chat_result`` in the BFF (apps/ds-insights-companion-ui/backend/orchestrator.py):

  summarized            -> ``insighter`` (the answer) + ``text2sql`` (SQL and rows)
  clarification_needed  -> ``message`` holds the follow-up question for the user
  return_response       -> ``message`` holds a Markdown document (chitchat, product brief)
  error                 -> ``message`` holds the error copy; the BFF also uses this
                           action when the orchestrator payload could not be parsed

Every turn gets exactly one classification. Only FULL_ANSWER and
VALID_DIRECT_RESPONSE are completed business outcomes. CLARIFICATION and
PARTIAL_ANSWER are valid system behaviour but an incomplete journey. Everything
else is a failure.

``followup_query_suggestions`` is optional metadata. It is captured separately and
never used as the primary answer.

This module has no Locust dependency so it can be unit-tested and reused by the
screening script.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

FULL_ANSWER = "FULL_ANSWER"
VALID_DIRECT_RESPONSE = "VALID_DIRECT_RESPONSE"
CLARIFICATION = "CLARIFICATION"
PARTIAL_ANSWER = "PARTIAL_ANSWER"
ROUTING_REFUSAL = "ROUTING_REFUSAL"
APPLICATION_ERROR = "APPLICATION_ERROR"
EMPTY_RESPONSE = "EMPTY_RESPONSE"
INCOMPLETE_STREAM = "INCOMPLETE_STREAM"
HTTP_ERROR = "HTTP_ERROR"
TIMEOUT = "TIMEOUT"
INVALID_CONTRACT = "INVALID_CONTRACT"

COMPLETED = frozenset({FULL_ANSWER, VALID_DIRECT_RESPONSE})
INCOMPLETE = frozenset({CLARIFICATION, PARTIAL_ANSWER})
FAILED = frozenset(
    {ROUTING_REFUSAL, APPLICATION_ERROR, EMPTY_RESPONSE, INCOMPLETE_STREAM, HTTP_ERROR, TIMEOUT, INVALID_CONTRACT}
)
ALL_CLASSIFICATIONS = COMPLETED | INCOMPLETE | FAILED

CHAT_ACTIONS = {"summarized", "clarification_needed", "return_response", "error"}

# Fixed error copy emitted by the orchestrator (src/graph/nodes/classify_and_route.py
# and the router prompt in src/agents/orchestrator/prompts.py). Matched by prefix
# because both are templates, not free text.
REFUSAL_PREFIXES = {
    "I could not tell which data this question is about": "unroutable",
    "This query does not fall within the supported data domains": "out_of_scope",
}
# Known application-failure copy, from the orchestrator and from the BFF's own fallbacks.
ERROR_PREFIXES = {
    # The caller lacks access to the sub-agent's data (returned in-band, HTTP 200, not 403).
    "You don't have access to the": "no_data_access",
    "LLM returned unknown domain": "router_unknown_domain",
    "Error calling router LLM": "router_error",
    "Guardrail validation error": "guardrail_error",
    "Genie message status": "genie_status",
    "All plan steps failed or were skipped": "all_steps_failed",
    "synthesise reached without an execution_plan": "synthesise_no_plan",
    "No user query found in messages": "no_user_query",
    "The assistant could not answer that question.": "bff_empty_error",
    "The assistant returned an unexpected response.": "bff_unexpected_response",
}

KINDS = {"data", "direct", "multi"}


@dataclass
class Question:
    id: str
    domain: str
    kind: str
    text: str
    subjects: list[list[str]] = field(default_factory=list)


def load_questions(path: str | Path) -> list[Question]:
    """Read ``id|domain|kind|question[|subjects]`` lines; # comments and blanks skipped."""
    questions: list[Question] = []
    for line_no, raw in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("|")
        if len(parts) not in (4, 5):
            raise ValueError(f"{path}:{line_no}: expected 4 or 5 '|'-separated fields, got {len(parts)}")
        qid, domain, kind, text = (p.strip() for p in parts[:4])
        if kind not in KINDS:
            raise ValueError(f"{path}:{line_no}: unknown kind {kind!r}")
        subjects = []
        if len(parts) == 5 and parts[4].strip():
            subjects = [[k.strip() for k in s.split(",") if k.strip()] for s in parts[4].split(";")]
        questions.append(Question(qid, domain, kind, text, subjects))
    ids = [q.id for q in questions]
    if len(ids) != len(set(ids)):
        raise ValueError(f"{path}: duplicate question ids")
    return questions


@dataclass
class ChatOutcome:
    classification: str
    reason: str
    http_status: int | None = None
    action: str | None = None
    session_id: str | None = None
    primary_answer: str = ""
    clarification: str = ""
    error_message: str = ""
    followups: list[str] = field(default_factory=list)
    sql_query_present: bool = False
    sql_row_count: int = 0
    sql_columns: list[str] = field(default_factory=list)
    subjects_addressed: list[bool] | None = None
    # What the original scenario accepted: HTTP 200 + a known action.
    legacy_pass: bool = False

    @property
    def completed(self) -> bool:
        return self.classification in COMPLETED

    @property
    def verdict(self) -> str:
        if self.classification in COMPLETED:
            return "complete"
        if self.classification in INCOMPLETE:
            return "incomplete"
        return "failed"

    def to_record(self) -> dict:
        """Sanitized record for evidence: no answer text, only its shape.

        Clarification, error copy and follow-up suggestions are system prose, not
        business data, so they are kept (truncated). The answer itself is reduced
        to its length, SQL to presence, and rows to a count plus column names.
        """
        return {
            "classification": self.classification,
            "verdict": self.verdict,
            "reason": self.reason,
            "http_status": self.http_status,
            "action": self.action,
            "session_id": self.session_id,
            "primary_answer_len": len(self.primary_answer),
            "clarification": self.clarification[:400],
            "error_message": self.error_message[:400],
            "followup_count": len(self.followups),
            "followups": [f[:200] for f in self.followups[:5]],
            "sql_query_present": self.sql_query_present,
            "sql_row_count": self.sql_row_count,
            "sql_columns": self.sql_columns[:20],
            "subjects_addressed": self.subjects_addressed,
            "followups_without_primary": bool(self.followups) and not self.primary_answer,
            "legacy_pass": self.legacy_pass,
        }


def _prefix_match(message: str, table: dict[str, str]) -> str | None:
    for prefix, reason in table.items():
        if message.startswith(prefix):
            return reason
    return None


def _error_reason(message: str) -> str:
    """Name an application-error message; flags the BFF fallback for multi-domain payloads."""
    known = _prefix_match(message, ERROR_PREFIXES)
    if known:
        return known
    try:
        payload = json.loads(message)
    except ValueError:
        payload = None
    if isinstance(payload, dict) and payload.get("action"):
        # to_chat_result could not normalise this orchestrator action and surfaced the raw text.
        return f"unparsed_action:{payload['action']}"
    return "unrecognised_error_message"


def _subjects_addressed(subjects: list[list[str]], texts: list[str]) -> list[bool]:
    # Column names use underscores (share_of_search); treat them as spaces so a
    # whole-word match still finds them.
    haystack = " ".join(texts).replace("_", " ")
    return [
        any(re.search(rf"\b{re.escape(k)}\b", haystack, re.IGNORECASE) for k in alternatives)
        for alternatives in subjects
    ]


def classify_chat_result(
    body: object,
    *,
    http_status: int | None = 200,
    kind: str = "data",
    subjects: list[list[str]] | None = None,
) -> ChatOutcome:
    """Classify a parsed ChatResult body (as returned by POST /api/chat)."""
    if not isinstance(body, dict):
        return ChatOutcome(INVALID_CONTRACT, "body_not_object", http_status=http_status)

    action = body.get("action")
    session_id = body.get("session_id") if isinstance(body.get("session_id"), str) else None
    if not (isinstance(session_id, str) and isinstance(body.get("user_query_id"), str) and action in CHAT_ACTIONS):
        return ChatOutcome(
            INVALID_CONTRACT, "missing_required_fields", http_status=http_status, action=str(action), session_id=session_id
        )

    followups = [s.strip() for s in body.get("followup_query_suggestions") or [] if isinstance(s, str) and s.strip()]
    message = body.get("message") if isinstance(body.get("message"), str) else ""
    message = message.strip()
    out = ChatOutcome("", "", http_status=http_status, action=action, session_id=session_id, followups=followups)
    out.legacy_pass = http_status == 200

    if action == "clarification_needed":
        out.clarification = message
        if not message:
            out.classification, out.reason = EMPTY_RESPONSE, "empty_clarification"
        else:
            out.classification, out.reason = CLARIFICATION, "clarification_needed"
        return out

    if action == "error":
        out.error_message = message
        refusal = _prefix_match(message, REFUSAL_PREFIXES)
        if refusal:
            out.classification, out.reason = ROUTING_REFUSAL, refusal
        else:
            out.classification, out.reason = APPLICATION_ERROR, _error_reason(message)
        return out

    if action == "return_response":
        out.primary_answer = message
        if not message:
            out.classification, out.reason = EMPTY_RESPONSE, "empty_document"
        elif kind == "direct":
            out.classification, out.reason = VALID_DIRECT_RESPONSE, "return_response"
        else:
            # A data question answered with a document means it never reached a data
            # domain (e.g. the chitchat agent explaining what it can do).
            out.classification, out.reason = ROUTING_REFUSAL, "document_for_data_question"
        return out

    # summarized
    insighter = body.get("insighter") if isinstance(body.get("insighter"), dict) else {}
    text2sql = body.get("text2sql") if isinstance(body.get("text2sql"), dict) else {}
    insight = insighter.get("insight") if isinstance(insighter.get("insight"), str) else ""
    rows = text2sql.get("sql_data") if isinstance(text2sql.get("sql_data"), list) else []
    sql_query = text2sql.get("sql_query") if isinstance(text2sql.get("sql_query"), str) else ""
    out.primary_answer = insight.strip()
    out.sql_query_present = bool(sql_query.strip())
    out.sql_row_count = len(rows)
    out.sql_columns = list(rows[0].keys()) if rows and isinstance(rows[0], dict) else []

    if not out.primary_answer:
        out.classification, out.reason = EMPTY_RESPONSE, "no_insight"
        return out
    if not rows:
        # The summarizer wrote prose, but no data came back to support it.
        out.classification, out.reason = EMPTY_RESPONSE, "no_rows" if out.sql_query_present else "no_sql_no_rows"
        return out

    if kind == "multi" and subjects:
        evidence = [out.primary_answer, *(e for e in insighter.get("supporting_evidence") or [] if isinstance(e, str))]
        evidence += out.sql_columns
        out.subjects_addressed = _subjects_addressed(subjects, evidence)
        if not all(out.subjects_addressed):
            out.classification, out.reason = PARTIAL_ANSWER, "not_all_subjects_addressed"
            return out

    out.classification, out.reason = FULL_ANSWER, "summarized_with_rows"
    return out


def classify_http_response(
    status_code: int | None,
    text: str | None,
    *,
    timed_out: bool = False,
    kind: str = "data",
    subjects: list[list[str]] | None = None,
) -> ChatOutcome:
    """Classify a blocking POST /api/chat response from its status and raw body text."""
    if timed_out:
        return ChatOutcome(TIMEOUT, "client_timeout", http_status=status_code)
    if status_code != 200:
        error_code = ""
        try:
            parsed = json.loads(text or "")
            error_code = parsed.get("error_code", "") if isinstance(parsed, dict) else ""
        except ValueError:
            pass
        if status_code == 504 or error_code == "upstream_timeout":
            return ChatOutcome(TIMEOUT, f"http_{status_code}:{error_code or 'gateway_timeout'}", http_status=status_code)
        return ChatOutcome(HTTP_ERROR, f"http_{status_code}:{error_code}", http_status=status_code)
    try:
        body = json.loads(text or "")
    except ValueError:
        return ChatOutcome(INVALID_CONTRACT, "body_not_json", http_status=status_code)
    return classify_chat_result(body, http_status=status_code, kind=kind, subjects=subjects)


def classify_stream_events(
    events: list[dict],
    *,
    http_status: int | None = 200,
    kind: str = "data",
    subjects: list[list[str]] | None = None,
) -> ChatOutcome:
    """Classify a POST /api/chat/stream turn from its parsed SSE ``data:`` events.

    The stream is always HTTP 200; failures arrive in-band as ``{"type": "error"}``,
    and a stream with no terminal ``{"type": "result"}`` never finished.
    """
    if http_status != 200:
        return ChatOutcome(HTTP_ERROR, f"http_{http_status}", http_status=http_status)
    for event in events:
        if isinstance(event, dict) and event.get("type") == "error":
            code = event.get("error_code", "")
            cls = TIMEOUT if code == "upstream_timeout" else APPLICATION_ERROR
            out = ChatOutcome(cls, f"stream_error:{code}", http_status=http_status)
            out.error_message = str(event.get("message") or "")
            return out
    for event in reversed(events):
        if isinstance(event, dict) and event.get("type") == "result":
            return classify_chat_result(event.get("result"), http_status=http_status, kind=kind, subjects=subjects)
    return ChatOutcome(INCOMPLETE_STREAM, "no_terminal_result_event", http_status=http_status)

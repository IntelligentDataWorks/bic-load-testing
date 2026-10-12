"""Unit tests for scenarios/chat_outcome.py.

Run from the repository root:  python -m pytest tests/python -q
(Playwright's testDir is ./tests but it only picks up *.spec.ts, so it ignores this folder.)
"""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scenarios"))

import chat_outcome as co  # noqa: E402


def chat(action, **extra):
    return {"session_id": "s-1", "user_query_id": "q-1", "action": action, **extra}


def summarized(insight="Adidas leads with 31%.", rows=None, sql="SELECT 1", followups=None, evidence=None):
    return chat(
        "summarized",
        insighter={"insight": insight, "supporting_evidence": evidence or []},
        text2sql={"sql_query": sql, "sql_data": [{"brand": "adidas", "sos": 31}] if rows is None else rows},
        followup_query_suggestions=followups or [],
    )


def test_summarized_with_rows_is_full_answer():
    out = co.classify_chat_result(summarized())
    assert out.classification == co.FULL_ANSWER
    assert out.completed and out.verdict == "complete"
    assert out.sql_row_count == 1 and out.sql_columns == ["brand", "sos"]


def test_summarized_without_rows_is_empty_response():
    out = co.classify_chat_result(summarized(rows=[]))
    assert out.classification == co.EMPTY_RESPONSE
    assert out.reason == "no_rows"
    out = co.classify_chat_result(summarized(rows=[], sql=""))
    assert out.reason == "no_sql_no_rows"


def test_followups_alone_never_count_as_an_answer():
    out = co.classify_chat_result(summarized(insight="  ", followups=["Show Nike too?"]))
    assert out.classification == co.EMPTY_RESPONSE
    assert out.followups == ["Show Nike too?"]
    assert out.to_record()["followups_without_primary"] is True
    assert out.legacy_pass is True  # the old HTTP-200 check would have passed it


def test_followups_are_captured_separately_from_the_answer():
    out = co.classify_chat_result(summarized(followups=["By quarter?", "By gender?"]))
    assert out.classification == co.FULL_ANSWER
    assert out.primary_answer == "Adidas leads with 31%."
    assert out.followups == ["By quarter?", "By gender?"]


def test_clarification_is_incomplete_not_complete():
    out = co.classify_chat_result(chat("clarification_needed", message="Which market do you mean?"))
    assert out.classification == co.CLARIFICATION
    assert out.verdict == "incomplete" and not out.completed
    assert out.clarification == "Which market do you mean?"


def test_empty_clarification_is_empty_response():
    assert co.classify_chat_result(chat("clarification_needed", message="")).classification == co.EMPTY_RESPONSE


@pytest.mark.parametrize(
    "message,reason",
    [
        ("I could not tell which data this question is about. Please name a metric ...", "unroutable"),
        ("This query does not fall within the supported data domains (AI.Vision, ...).", "out_of_scope"),
    ],
)
def test_router_templates_are_routing_refusals(message, reason):
    out = co.classify_chat_result(chat("error", message=message))
    assert out.classification == co.ROUTING_REFUSAL
    assert out.reason == reason and out.verdict == "failed"


@pytest.mark.parametrize(
    "message,reason",
    [
        ("Genie message status: FAILED", "genie_status"),
        ("You don't have access to the 'ProductReviews' data source. Contact your workspace admin.", "no_data_access"),
        ("The assistant returned an unexpected response.", "bff_unexpected_response"),
        ("something new went wrong", "unrecognised_error_message"),
        (json.dumps({"action": "send_to_join_resolver", "domains": ["A", "B"]}), "unparsed_action:send_to_join_resolver"),
    ],
)
def test_other_error_actions_are_application_errors(message, reason):
    out = co.classify_chat_result(chat("error", message=message))
    assert out.classification == co.APPLICATION_ERROR
    assert out.reason == reason


def test_document_is_valid_direct_response_only_for_direct_questions():
    body = chat("return_response", message="# Product brief\n...")
    assert co.classify_chat_result(body, kind="direct").classification == co.VALID_DIRECT_RESPONSE
    assert co.classify_chat_result(body, kind="data").classification == co.ROUTING_REFUSAL
    assert co.classify_chat_result(chat("return_response", message=""), kind="direct").classification == co.EMPTY_RESPONSE


def test_multi_domain_needs_every_subject():
    subjects = [["MBV", "buying volume"], ["share of search", "SoS"]]
    mbv_rows = [{"model": "Samba", "mbv": 1}]
    both = summarized(insight="Samba MBV was 1.2M; it ranks #3 in share of search in Germany.", rows=mbv_rows)
    one = summarized(insight="Samba MBV in SS26 was 1.2M pairs.", rows=mbv_rows)
    via_column = summarized(insight="Samba MBV was 1.2M.", rows=[{"mbv": 1, "share_of_search": 0.1}])
    assert co.classify_chat_result(via_column, kind="multi", subjects=subjects).classification == co.FULL_ANSWER
    # whole words only: "sos" inside another word must not count
    lookalike = summarized(insight="Samba MBV was 1.2M, as in prior seasons.", rows=[{"mbv": 1, "tsos": 2}])
    assert co.classify_chat_result(lookalike, kind="multi", subjects=subjects).classification == co.PARTIAL_ANSWER
    assert co.classify_chat_result(both, kind="multi", subjects=subjects).classification == co.FULL_ANSWER
    partial = co.classify_chat_result(one, kind="multi", subjects=subjects)
    assert partial.classification == co.PARTIAL_ANSWER
    assert partial.subjects_addressed == [True, False] and partial.verdict == "incomplete"


@pytest.mark.parametrize(
    "body",
    [
        [],
        {"action": "summarized"},
        chat("mystery"),
        {"session_id": 1, "user_query_id": "q", "action": "error"},
    ],
)
def test_contract_violations_are_invalid_contract(body):
    assert co.classify_chat_result(body).classification == co.INVALID_CONTRACT


def test_http_level_outcomes():
    assert co.classify_http_response(None, None, timed_out=True).classification == co.TIMEOUT
    assert co.classify_http_response(504, '{"error_code":"upstream_timeout"}').classification == co.TIMEOUT
    assert co.classify_http_response(502, '{"error_code":"upstream_error"}').classification == co.HTTP_ERROR
    assert co.classify_http_response(403, "{}").classification == co.HTTP_ERROR
    assert co.classify_http_response(200, "<html>").classification == co.INVALID_CONTRACT
    assert co.classify_http_response(200, json.dumps(summarized())).classification == co.FULL_ANSWER


def test_stream_outcomes():
    result = {"type": "result", "result": summarized()}
    assert co.classify_stream_events([{"type": "status"}, result]).classification == co.FULL_ANSWER
    assert co.classify_stream_events([{"type": "status"}]).classification == co.INCOMPLETE_STREAM
    err = co.classify_stream_events([{"type": "error", "error_code": "internal_error", "message": "x"}])
    assert err.classification == co.APPLICATION_ERROR
    assert co.classify_stream_events([{"type": "error", "error_code": "upstream_timeout"}]).classification == co.TIMEOUT


def test_record_is_sanitized():
    rec = co.classify_chat_result(summarized(insight="Net sales were EUR 12,345,678.")).to_record()
    assert "Net sales" not in json.dumps(rec)
    assert "12,345,678" not in json.dumps(rec)
    assert rec["primary_answer_len"] == len("Net sales were EUR 12,345,678.")


def test_every_classification_has_one_verdict():
    assert co.COMPLETED.isdisjoint(co.INCOMPLETE) and co.COMPLETED.isdisjoint(co.FAILED)
    assert co.INCOMPLETE.isdisjoint(co.FAILED)
    assert len(co.ALL_CLASSIFICATIONS) == 11


def test_approved_catalogue_loads():
    qs = co.load_questions(ROOT / "data" / "approved_questions.txt")
    assert len(qs) == 43
    assert [q.id for q in qs] == [f"Q{i:02d}" for i in range(1, 44)]
    counts = {}
    for q in qs:
        counts[q.domain] = counts.get(q.domain, 0) + 1
    assert counts == {
        "AI.Vision": 5, "ShareOfSearch": 5, "RangeInsights": 6, "ProductReviews": 5, "FinanceInsights": 6,
        "ProductBrief": 4, "ProductBriefFootball": 3, "Chitchat": 8, "Multi-Domain": 1,
    }
    multi = [q for q in qs if q.kind == "multi"]
    assert len(multi) == 1 and len(multi[0].subjects) == 2

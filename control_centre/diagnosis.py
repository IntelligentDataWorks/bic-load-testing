"""LLM diagnosis of a completed run.

A compact, sanitized summary of the run -- configuration, aggregate and
per-endpoint metrics, failure/exception counts, Playwright outcomes and the
configured thresholds -- is sent to a Databricks serving or AI Gateway endpoint.

What is deliberately *not* sent: bearer tokens, authorization headers, the
Playwright storage-state file, raw response bodies and any business data. The
payload is assembled from parsed metrics only, then passed through the same
redaction filter used for logs as a second line of defence.

The adapter is small and isolated: the repo has no Databricks SDK or OpenAI
client dependency, so this speaks the serving-endpoint REST contract directly
with ``requests`` (already present via Locust).
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

import requests

from control_centre.auth import TokenBundle
from control_centre.locust_results import LocustResults
from control_centre.locust_results import summarise_for_diagnosis as summarise_locust
from control_centre.playwright_results import PlaywrightResults
from control_centre.playwright_results import summarise_for_diagnosis as summarise_playwright
from control_centre.redaction import redact
from control_centre.runs import RunManifest
from control_centre.settings import AppSettings

SYSTEM_PROMPT = """You are a performance-test analyst reviewing one automated test run.

Rules you must follow:
- Base every finding ONLY on the metrics supplied in the user message. Do not invent
  numbers, endpoints, errors or causes that are not present.
- When you infer a cause rather than observe it, prefix it with "Inferred:".
- If the sample size is too small for percentiles to be meaningful, say so explicitly.
- A single load-test identity means all virtual users share one Databricks principal;
  call this out when it limits what the run can prove.
- Be concise and specific. No filler.

Respond with a single JSON object and nothing else, using exactly these keys:
{
  "overall_status": "Pass" | "Conditional Pass" | "Fail",
  "executive_summary": "2-4 sentences a non-engineer can act on",
  "key_findings": ["..."],
  "likely_bottleneck": "...",
  "threshold_breaches": ["..."],
  "auth_findings": ["..."],
  "top_errors": ["..."],
  "recommended_next_action": "...",
  "limitations": ["..."]
}"""

_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)


@dataclass
class DiagnosisRequestSummary:
    """The exact, sanitized object sent to the model. Shown to the user on request."""

    run: dict[str, Any]
    thresholds: dict[str, Any]
    locust: dict[str, Any] | None = None
    playwright: dict[str, Any] | None = None
    notes: list[str] = field(default_factory=list)


@dataclass
class Diagnosis:
    ok: bool
    overall_status: str = ""
    executive_summary: str = ""
    key_findings: list[str] = field(default_factory=list)
    likely_bottleneck: str = ""
    threshold_breaches: list[str] = field(default_factory=list)
    auth_findings: list[str] = field(default_factory=list)
    top_errors: list[str] = field(default_factory=list)
    recommended_next_action: str = ""
    limitations: list[str] = field(default_factory=list)
    raw_text: str = ""
    error: str = ""
    endpoint: str = ""
    generated_at: str = ""
    request_summary: dict[str, Any] = field(default_factory=dict)

    def to_markdown(self) -> str:
        def bullets(items: list[str]) -> str:
            return "\n".join(f"- {item}" for item in items) if items else "- (none reported)"

        return "\n".join(
            [
                f"# AI diagnosis -- {self.overall_status or 'unknown'}",
                "",
                f"_Generated {self.generated_at} via `{self.endpoint}`_",
                "",
                "## Executive summary",
                self.executive_summary or "(none)",
                "",
                "## Key findings",
                bullets(self.key_findings),
                "",
                "## Likely bottleneck",
                self.likely_bottleneck or "(none identified)",
                "",
                "## Threshold breaches",
                bullets(self.threshold_breaches),
                "",
                "## Authentication / authorization findings",
                bullets(self.auth_findings),
                "",
                "## Most important errors",
                bullets(self.top_errors),
                "",
                "## Recommended next action",
                self.recommended_next_action or "(none)",
                "",
                "## Limitations",
                bullets(self.limitations),
                "",
            ]
        )

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True)


def build_request_summary(
    manifest: RunManifest,
    settings: AppSettings,
    locust: LocustResults | None = None,
    playwright: PlaywrightResults | None = None,
) -> DiagnosisRequestSummary:
    """Assemble the compact, sanitized summary for the model."""
    run_info = {
        "run_id": manifest.run_id,
        "kind": manifest.kind,
        "area": manifest.area,
        "profile": manifest.profile,
        "environment": manifest.environment,
        "auth_method": manifest.auth_method,
        "status": manifest.status,
        "exit_code": manifest.exit_code,
        "duration_seconds": manifest.duration_seconds,
        "config": manifest.config,
    }
    notes: list[str] = list(manifest.notes)
    if manifest.auth_method in {"oauth_u2m", "pat"}:
        notes.append(
            "All virtual users shared a single Databricks identity (one token), "
            "so per-user isolation and per-user rate limits are not exercised."
        )

    summary = DiagnosisRequestSummary(
        run=run_info,
        thresholds=asdict(settings.thresholds),
        locust=summarise_locust(locust) if locust and locust.found else None,
        playwright=summarise_playwright(playwright) if playwright and playwright.found else None,
        notes=notes,
    )
    if summary.locust and summary.locust.get("small_sample"):
        summary.notes.append(
            "Request count is below the meaningful-percentile threshold; "
            "percentiles reflect one or two samples."
        )
    return summary


def _sanitize(payload: Any) -> Any:
    """Recursively redact strings anywhere in the payload before it leaves the machine."""
    if isinstance(payload, str):
        return redact(payload)
    if isinstance(payload, dict):
        return {key: _sanitize(value) for key, value in payload.items()}
    if isinstance(payload, list):
        return [_sanitize(item) for item in payload]
    return payload


def _build_body(settings: AppSettings, user_content: str) -> dict[str, Any]:
    if settings.diagnosis.payload_style == "responses_agent":
        # MLflow ResponsesAgent contract, as used by this repo's own agent endpoint.
        return {
            "input": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ]
        }
    # OpenAI-compatible chat completions -- AI Gateway and foundation-model endpoints.
    return {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        "max_tokens": settings.diagnosis.max_tokens,
        "temperature": settings.diagnosis.temperature,
    }


def _extract_text(payload: Any) -> str:
    """Pull assistant text out of either supported response shape."""
    if isinstance(payload, str):
        return payload
    if not isinstance(payload, dict):
        return ""

    # OpenAI-compatible
    choices = payload.get("choices")
    if isinstance(choices, list) and choices:
        message = choices[0].get("message") or {}
        content = message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "".join(part.get("text", "") for part in content if isinstance(part, dict))

    # MLflow ResponsesAgent
    output = payload.get("output")
    if isinstance(output, list):
        chunks: list[str] = []
        for item in output:
            if not isinstance(item, dict):
                continue
            content = item.get("content")
            if isinstance(content, str):
                chunks.append(content)
            elif isinstance(content, list):
                chunks.extend(
                    part.get("text", "") for part in content if isinstance(part, dict)
                )
        if chunks:
            return "".join(chunks)

    for key in ("message", "text", "predictions"):
        value = payload.get(key)
        if isinstance(value, str):
            return value
    return ""


def _parse_structured(text: str) -> dict[str, Any]:
    match = _JSON_BLOCK_RE.search(text or "")
    if not match:
        return {}
    try:
        parsed = json.loads(match.group(0))
    except ValueError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def diagnose(
    summary: DiagnosisRequestSummary,
    settings: AppSettings,
    token: TokenBundle | None,
) -> Diagnosis:
    """Send the summary to the configured endpoint and parse the structured reply."""
    config = settings.diagnosis
    endpoint = f"{config.workspace_host.rstrip('/')}/serving-endpoints/{config.endpoint_name}/invocations"
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    if not token:
        return Diagnosis(
            ok=False,
            error="No token held. Authenticate on the Authentication page first.",
            endpoint=endpoint,
            generated_at=generated_at,
        )
    if not config.endpoint_name:
        return Diagnosis(
            ok=False,
            error="No diagnosis endpoint configured. Set one in AI diagnosis > settings.",
            endpoint=endpoint,
            generated_at=generated_at,
        )

    sanitized = _sanitize(asdict(summary))
    user_content = (
        "Diagnose this test run. All available data is below as JSON.\n\n"
        + json.dumps(sanitized, indent=2, sort_keys=True, default=str)
    )
    body = _build_body(settings, user_content)

    try:
        response = requests.post(
            endpoint,
            json=body,
            headers={
                "Authorization": f"Bearer {token.value}",
                "Content-Type": "application/json",
            },
            timeout=config.timeout_seconds,
        )
    except requests.Timeout:
        return Diagnosis(
            ok=False,
            error=f"Request timed out after {config.timeout_seconds}s.",
            endpoint=endpoint,
            generated_at=generated_at,
            request_summary=sanitized,
        )
    except requests.RequestException as exc:
        return Diagnosis(
            ok=False,
            error=redact(f"Request failed: {exc}"),
            endpoint=endpoint,
            generated_at=generated_at,
            request_summary=sanitized,
        )

    if response.status_code != 200:
        hint = ""
        if response.status_code in (401, 403):
            hint = " The held token may be expired, or it may not be authorised for this endpoint."
        return Diagnosis(
            ok=False,
            error=redact(f"HTTP {response.status_code}: {response.text[:400]}{hint}"),
            endpoint=endpoint,
            generated_at=generated_at,
            request_summary=sanitized,
        )

    try:
        payload = response.json()
    except ValueError:
        return Diagnosis(
            ok=False,
            error="Endpoint response was not JSON.",
            endpoint=endpoint,
            generated_at=generated_at,
            request_summary=sanitized,
        )

    text = redact(_extract_text(payload))
    structured = _parse_structured(text)
    if not structured:
        return Diagnosis(
            ok=False,
            error="Model reply was not the requested JSON object.",
            raw_text=text[:4000],
            endpoint=endpoint,
            generated_at=generated_at,
            request_summary=sanitized,
        )

    def as_list(value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(item) for item in value]
        return [str(value)] if value else []

    return Diagnosis(
        ok=True,
        overall_status=str(structured.get("overall_status", "")),
        executive_summary=str(structured.get("executive_summary", "")),
        key_findings=as_list(structured.get("key_findings")),
        likely_bottleneck=str(structured.get("likely_bottleneck", "")),
        threshold_breaches=as_list(structured.get("threshold_breaches")),
        auth_findings=as_list(structured.get("auth_findings")),
        top_errors=as_list(structured.get("top_errors")),
        recommended_next_action=str(structured.get("recommended_next_action", "")),
        limitations=as_list(structured.get("limitations")),
        raw_text=text,
        endpoint=endpoint,
        generated_at=generated_at,
        request_summary=sanitized,
    )


def attach_to_manifest(manifest: RunManifest, diagnosis: Diagnosis) -> None:
    """Record the diagnosis (without the request payload) alongside the run."""
    record = asdict(diagnosis)
    record.pop("request_summary", None)
    manifest.diagnosis = record
    manifest.save()

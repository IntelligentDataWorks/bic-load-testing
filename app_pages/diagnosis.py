"""AI diagnosis: send a compact, sanitized run summary to a Databricks endpoint."""

from __future__ import annotations

import json

import streamlit as st

import app_state
import ui_components as ui
from control_centre.auth import fetch_oauth_token
from control_centre.diagnosis import (
    Diagnosis,
    attach_to_manifest,
    build_request_summary,
    diagnose,
)
from control_centre.locust_results import parse_locust_results
from control_centre.models import AuthMethod
from control_centre.playwright_results import parse_playwright_results
from control_centre.runs import RunManifest, list_manifests
from control_centre.settings import Thresholds

settings = app_state.settings()

st.title("AI diagnosis", icon=":material/psychology:")
st.caption(
    "Sends only parsed metrics: configuration, aggregate and per-endpoint numbers, failure and "
    "exception summaries, Playwright outcomes and your thresholds. No tokens, no authorization "
    "headers, no auth files, no raw response bodies."
)

manifests = [m for m in list_manifests() if m.status_enum.is_terminal]
if not manifests:
    st.info("No completed runs to diagnose yet.", icon=":material/info:")
    st.stop()

run_ids = [m.run_id for m in manifests]
selected = app_state.selected_run()
index = run_ids.index(selected) if selected in run_ids else 0
chosen = st.selectbox("Completed run", run_ids, index=index, key="diag_run_choice")
app_state.set_selected_run(chosen)
manifest: RunManifest = next(m for m in manifests if m.run_id == chosen)
ui.run_header(manifest)

# --------------------------------------------------------------------------
# Endpoint settings
# --------------------------------------------------------------------------
with st.expander("Diagnosis endpoint settings", icon=":material/settings:", expanded=not settings.diagnosis.endpoint_name):
    row = st.columns(2)
    workspace_host = row[0].text_input(
        "Databricks workspace host", value=settings.diagnosis.workspace_host, key="diag_host"
    ).strip()
    endpoint_name = row[1].text_input(
        "AI Gateway / serving endpoint name",
        value=settings.diagnosis.endpoint_name,
        key="diag_endpoint",
        help="Must exist in that workspace, e.g. a foundation-model or AI Gateway endpoint.",
    ).strip()

    row2 = st.columns(3)
    payload_style = row2[0].selectbox(
        "Request shape",
        ["chat", "responses_agent"],
        index=0 if settings.diagnosis.payload_style == "chat" else 1,
        key="diag_style",
        help=(
            "'chat' is the OpenAI-compatible {messages: [...]} contract used by AI Gateway and "
            "foundation-model endpoints. 'responses_agent' is the MLflow {input: [...]} contract "
            "this repo's own agent endpoint speaks."
        ),
    )
    timeout = int(
        row2[1].number_input(
            "Timeout (seconds)", min_value=10, max_value=900, value=settings.diagnosis.timeout_seconds, key="diag_timeout"
        )
    )
    max_tokens = int(
        row2[2].number_input(
            "Max tokens", min_value=200, max_value=8000, value=settings.diagnosis.max_tokens, step=100, key="diag_tokens"
        )
    )

    st.caption(
        "Authentication reuses the token held in this session. OAuth U2M is preferred; a PAT is "
        "accepted by standard Model Serving endpoints."
    )

    st.markdown("**Thresholds sent with the metrics**")
    trow = st.columns(4)
    thresholds = Thresholds(
        max_failure_pct=float(
            trow[0].number_input("Max failure %", 0.0, 100.0, settings.thresholds.max_failure_pct, key="thr_fail")
        ),
        max_p95_ms=float(
            trow[1].number_input("Max p95 (ms)", 100.0, 600_000.0, settings.thresholds.max_p95_ms, step=500.0, key="thr_p95")
        ),
        max_avg_ms=float(
            trow[2].number_input("Max avg (ms)", 100.0, 600_000.0, settings.thresholds.max_avg_ms, step=500.0, key="thr_avg")
        ),
        max_playwright_journey_ms=float(
            trow[3].number_input(
                "Max UI journey (ms)", 1000.0, 1_800_000.0, settings.thresholds.max_playwright_journey_ms, step=5000.0, key="thr_ui"
            )
        ),
    )

    if st.button("Save diagnosis settings", icon=":material/save:"):
        settings.diagnosis.workspace_host = workspace_host
        settings.diagnosis.endpoint_name = endpoint_name
        settings.diagnosis.payload_style = payload_style
        settings.diagnosis.timeout_seconds = timeout
        settings.diagnosis.max_tokens = max_tokens
        settings.thresholds = thresholds
        app_state.save_settings(settings)
        st.success("Saved.", icon=":material/check_circle:")
        st.rerun()

# --------------------------------------------------------------------------
# Build the payload
# --------------------------------------------------------------------------
locust = (
    parse_locust_results(manifest.artifacts["locust_csv_prefix"], manifest.artifacts.get("locust_html"))
    if "locust_csv_prefix" in manifest.artifacts
    else None
)
playwright = (
    parse_playwright_results(manifest.artifacts["playwright_json"])
    if "playwright_json" in manifest.artifacts
    else None
)
summary = build_request_summary(manifest, settings, locust, playwright)

with st.expander("Exactly what will be sent", icon=":material/visibility:"):
    st.json(json.loads(json.dumps(summary.__dict__, default=str)))

token = app_state.token()
if token is None or token.is_expired:
    diag_host = settings.diagnosis.workspace_host or settings.default_workspace_host
    with st.container(border=True):
        st.warning(
            "No token held in this browser session."
            if token is None
            else "The held token has expired.",
            icon=":material/warning:",
        )
        st.caption(
            "Tokens live in this tab's session memory only, so a page refresh, a new tab or a "
            "Streamlit restart clears them. A PAT is not required -- an OAuth U2M token works."
        )
        if st.button(
            f"Get OAuth token for {diag_host}",
            icon=":material/key:",
            disabled=not diag_host,
        ):
            with st.spinner("Requesting a token from the Databricks CLI..."):
                new_bundle, error = fetch_oauth_token(diag_host)
            if new_bundle is None:
                st.error(error, icon=":material/error:")
                st.page_link(
                    "app_pages/authentication.py",
                    label="Open Authentication (browser sign-in or PAT)",
                    icon=":material/login:",
                )
            else:
                app_state.set_token(new_bundle, AuthMethod.OAUTH_U2M)
                st.rerun()

ready = token is not None and not token.is_expired and bool(settings.diagnosis.endpoint_name)
if st.button("Diagnose results", icon=":material/psychology:", type="primary", disabled=not ready):
    with st.spinner("Asking the model..."):
        result = diagnose(summary, settings, token)
    st.session_state[f"diagnosis:{manifest.run_id}"] = result
    if result.ok:
        attach_to_manifest(manifest, result)

stored: Diagnosis | None = st.session_state.get(f"diagnosis:{manifest.run_id}")
if stored is None and manifest.diagnosis:
    stored = Diagnosis(**{k: v for k, v in manifest.diagnosis.items() if k in Diagnosis.__dataclass_fields__})

if stored is None:
    st.caption("No diagnosis has been generated for this run yet.")
    st.stop()

if not stored.ok:
    st.error(stored.error or "Diagnosis failed.", icon=":material/error:")
    if stored.raw_text:
        with st.expander("Raw model reply", icon=":material/code:"):
            st.code(stored.raw_text, language="text", wrap_lines=True)
    st.stop()

# --------------------------------------------------------------------------
# Render
# --------------------------------------------------------------------------
status_color = {
    "Pass": "green",
    "Conditional Pass": "orange",
    "Fail": "red",
}.get(stored.overall_status, "gray")

with st.container(border=True):
    with st.container(horizontal=True, vertical_alignment="center"):
        st.badge(stored.overall_status or "unknown", color=status_color, icon=":material/rule:")
        st.caption(f"Generated {ui.format_timestamp(stored.generated_at)}")
    st.markdown(stored.executive_summary or "(no summary returned)")
    if stored.recommended_next_action:
        st.markdown(f"**Next action:** {stored.recommended_next_action}")

with st.expander("Technical detail", icon=":material/troubleshoot:", expanded=False):
    st.markdown("**Key findings**")
    for item in stored.key_findings or ["(none)"]:
        st.markdown(f"- {item}")
    st.markdown("**Likely bottleneck**")
    st.markdown(stored.likely_bottleneck or "(none identified)")
    st.markdown("**Threshold breaches**")
    for item in stored.threshold_breaches or ["(none)"]:
        st.markdown(f"- {item}")
    st.markdown("**Authentication / authorization findings**")
    for item in stored.auth_findings or ["(none)"]:
        st.markdown(f"- {item}")
    st.markdown("**Most important errors**")
    for item in stored.top_errors or ["(none)"]:
        st.markdown(f"- {item}")
    st.markdown("**Limitations**")
    for item in stored.limitations or ["(none)"]:
        st.markdown(f"- {item}")

with st.container(horizontal=True):
    st.download_button(
        "Download Markdown",
        data=stored.to_markdown().encode("utf-8"),
        file_name=f"{manifest.run_id}-diagnosis.md",
        mime="text/markdown",
        icon=":material/download:",
        key="dl_diag_md",
    )
    st.download_button(
        "Download JSON",
        data=stored.to_json().encode("utf-8"),
        file_name=f"{manifest.run_id}-diagnosis.json",
        mime="application/json",
        icon=":material/download:",
        key="dl_diag_json",
    )
st.caption(
    f"The diagnosis is attached to `results/{manifest.run_id}/manifest.json` so it travels with the run."
)

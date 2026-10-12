"""Dashboard: what is available, what is authenticated, what ran last."""

from __future__ import annotations

import streamlit as st

import app_state
import ui_components as ui
from control_centre.discovery import (
    discover_locust_profiles,
    discover_locust_scenarios,
    discover_playwright_tests,
    refresh_all,
)
from control_centre.models import RunStatus, TestArea
from control_centre.runs import list_manifests

settings = app_state.settings()
registry = app_state.get_registry()

st.title("BIC load-testing control centre", icon=":material/speed:")
st.caption(
    "Run the repository's Locust scenarios and Playwright specs from one place. "
    "The runner is local; the targets are usually deployed Databricks services."
)

profiles = discover_locust_profiles()
scenarios = discover_locust_scenarios()
tests = discover_playwright_tests()
manifests = list_manifests(limit=50)

cols = st.columns(4)
cols[0].metric("Locust profiles", len(profiles), icon=":material/settings_applications:", border=True)
cols[1].metric("Locust scenarios", len(scenarios), icon=":material/code:", border=True)
cols[2].metric("Playwright specs", len(tests), icon=":material/web:", border=True)
cols[3].metric("Recorded runs", len(manifests), icon=":material/history:", border=True)

active = registry.active_runs()
if active:
    run = active[0]
    with st.container(border=True):
        with st.container(horizontal=True, vertical_alignment="center"):
            ui.status_badge(RunStatus.RUNNING)
            st.markdown(f"**{run.manifest.run_id}** against `{run.manifest.environment}`")
            st.caption(ui.format_duration(run.manifest.duration_seconds))
        with st.container(horizontal=True):
            if st.button("Open live logs", icon=":material/terminal:"):
                st.switch_page("app_pages/live_logs.py")
            if st.button("Stop run", icon=":material/stop_circle:", type="primary"):
                registry.stop(run.manifest.run_id)
                st.rerun()

st.subheader("Start here", icon=":material/flag:")
with st.container(horizontal=True, wrap=True):
    if st.button("Configure a test", icon=":material/tune:", type="primary"):
        st.switch_page("app_pages/configure.py")
    if st.button("Authenticate", icon=":material/key:"):
        st.switch_page("app_pages/authentication.py")
    if st.button("Review results", icon=":material/analytics:"):
        st.switch_page("app_pages/results.py")
    if st.button("Rescan repository", icon=":material/refresh:"):
        refresh_all()
        st.cache_data.clear()
        st.toast("Rescanned profiles, scenarios and specs.", icon=":material/refresh:")
        st.rerun()

left, right = st.columns([3, 2])

with left:
    st.subheader("Recent runs", icon=":material/history:")
    if not manifests:
        st.caption("No runs recorded yet. Configure a test to get started.")
    else:
        rows = [
            {
                "Run": m.run_id,
                "Kind": m.kind,
                "Status": m.status,
                "Duration": ui.format_duration(m.duration_seconds),
                "Target": m.environment,
                "Started": ui.format_timestamp(m.started_at),
            }
            for m in manifests[:10]
        ]
        st.dataframe(rows, hide_index=True)
        chosen = st.selectbox(
            "Open a run",
            [m.run_id for m in manifests[:10]],
            index=None,
            placeholder="Select a run id",
        )
        if chosen:
            app_state.set_selected_run(chosen)
            st.switch_page("app_pages/results.py")

with right:
    st.subheader("Environment", icon=":material/host:")
    checks = app_state.cached_toolchain_checks()
    ui.check_list(checks, title="Toolchain")

    storage = app_state.storage_state()
    with st.container(border=True):
        st.caption("Playwright browser session")
        st.markdown(f"**{storage.status_text}**")
        if storage.modified:
            st.caption(f"Saved {ui.format_timestamp(storage.modified.isoformat())}")
        if not storage.looks_usable:
            st.caption(f"{storage.problem} Capture a fresh session on the Authentication page.")
        elif storage.app_session_expiry:
            st.caption(f"App session expires {ui.format_timestamp(storage.app_session_expiry.isoformat())}")

    bundle = app_state.token()
    with st.container(border=True):
        st.caption("Databricks token")
        if bundle is None:
            st.markdown("**Not authenticated**")
        elif bundle.is_expired:
            st.markdown("**Expired**")
        else:
            remaining = bundle.expires_in_seconds
            st.markdown(f"**Held ({bundle.source})**")
            if remaining is not None:
                st.caption(f"Expires in {ui.format_duration(remaining)}")
        st.caption("The token value is never displayed, logged or written to disk.")

st.subheader("What each area covers", icon=":material/layers:")
area_cols = st.columns(3)
with area_cols[0].container(border=True, height="stretch"):
    st.markdown(f"**{TestArea.BFF.label}**")
    st.caption(
        "Locust against the FastAPI BFF -- health, identity, data sources, chat and "
        "streaming chat. Includes the Databricks Apps proxy when the target is deployed. "
        "Excludes the React UI."
    )
with area_cols[1].container(border=True, height="stretch"):
    st.markdown(f"**{TestArea.UI.label}**")
    st.caption(
        "Playwright in real Chromium against the deployed React app. Covers what a user "
        "actually experiences: rendering, session creation, the streaming answer. "
        "One browser journey, not concurrency."
    )
with area_cols[2].container(border=True, height="stretch"):
    st.markdown(f"**{TestArea.SERVING.label}**")
    st.caption(
        "Locust straight at /serving-endpoints/.../invocations. Excludes React and the "
        "BFF, but still exercises the agent orchestrator and everything downstream of it."
    )

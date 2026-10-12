"""Run history: every recorded run, filterable, with its manifest."""

from __future__ import annotations

import streamlit as st

import app_state
import ui_components as ui
from control_centre.runs import list_manifests

st.title("Run history", icon=":material/history:")
st.caption(
    "Every run writes results/<run-id>/manifest.json with its configuration, timings, status, "
    "exit code, artefact paths and a redacted command. Secrets are never recorded."
)

manifests = list_manifests()
if not manifests:
    st.info("No runs recorded yet.", icon=":material/info:")
    st.stop()

kinds = sorted({m.kind for m in manifests})
statuses = sorted({m.status for m in manifests})

filters = st.columns(3)
kind_filter = filters[0].pills("Kind", kinds, selection_mode="multi", key="hist_kind")
status_filter = filters[1].pills("Status", statuses, selection_mode="multi", key="hist_status")
search = filters[2].text_input(
    "Search", value="", type="search", placeholder="run id, profile or host", key="hist_search"
).strip().lower()

filtered = [
    m
    for m in manifests
    if (not kind_filter or m.kind in kind_filter)
    and (not status_filter or m.status in status_filter)
    and (
        not search
        or search in m.run_id.lower()
        or search in (m.profile or "").lower()
        or search in (m.environment or "").lower()
    )
]

st.caption(f"{len(filtered)} of {len(manifests)} runs")
st.dataframe(
    [
        {
            "Run": m.run_id,
            "Kind": m.kind,
            "Status": m.status,
            "Profile": m.profile,
            "Target": m.environment,
            "Started": ui.format_timestamp(m.started_at),
            "Duration": ui.format_duration(m.duration_seconds),
            "Exit": "-" if m.exit_code is None else m.exit_code,
            "Diagnosed": "yes" if m.diagnosis else "",
        }
        for m in filtered
    ]
    or [{"Run": "no matches"}],
    hide_index=True,
)

if not filtered:
    st.stop()

chosen = st.selectbox("Inspect a run", [m.run_id for m in filtered], key="hist_pick")
manifest = next(m for m in filtered if m.run_id == chosen)

ui.run_header(manifest)
with st.container(horizontal=True, wrap=True):
    if st.button("Open results", icon=":material/analytics:", type="primary"):
        app_state.set_selected_run(manifest.run_id)
        st.switch_page("app_pages/results.py")
    if st.button("Open AI diagnosis", icon=":material/psychology:"):
        app_state.set_selected_run(manifest.run_id)
        st.switch_page("app_pages/diagnosis.py")

with st.expander("Manifest", icon=":material/data_object:"):
    st.json(
        {
            "run_id": manifest.run_id,
            "area": manifest.area,
            "kind": manifest.kind,
            "profile": manifest.profile,
            "environment": manifest.environment,
            "auth_method": manifest.auth_method,
            "status": manifest.status,
            "exit_code": manifest.exit_code,
            "started_at": manifest.started_at,
            "ended_at": manifest.ended_at,
            "config": manifest.config,
            "artifacts": manifest.artifacts,
            "env_keys": manifest.env_keys,
            "redacted_commands": manifest.redacted_commands,
            "notes": manifest.notes,
        }
    )

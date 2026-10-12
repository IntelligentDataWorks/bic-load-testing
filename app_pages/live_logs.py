"""Live logs: streaming output, elapsed time and a safe stop button."""

from __future__ import annotations

import streamlit as st

import app_state
import ui_components as ui
from control_centre.models import RunStatus
from control_centre.runs import RunManifest

settings = app_state.settings()
registry = app_state.get_registry()

st.title("Live logs", icon=":material/terminal:")

runs = registry.all_runs()
if not runs:
    st.info("No run has been started in this session yet.", icon=":material/info:")
    if st.button("Configure a test", icon=":material/tune:", type="primary"):
        st.switch_page("app_pages/configure.py")
    st.stop()

active = registry.active_runs()
default_id = active[0].manifest.run_id if active else (app_state.active_run_id() or runs[-1].manifest.run_id)
run_ids = [r.manifest.run_id for r in runs]
chosen = st.selectbox(
    "Run",
    run_ids,
    index=run_ids.index(default_id) if default_id in run_ids else len(run_ids) - 1,
    key="log_run_choice",
)
run = registry.get(chosen)
if run is None:
    st.error("That run is no longer tracked in this session.", icon=":material/error:")
    st.stop()

st.caption(
    "Output is redacted before it is shown or written to results/<run-id>/run.log -- bearer "
    "headers, Databricks tokens and JWT-shaped strings are masked."
)


@st.fragment(run_every=f"{settings.auto_refresh_seconds}s")
def live_panel() -> None:
    """Refreshes on its own while the run is active; stops once it finishes."""
    manifest: RunManifest = run.manifest
    with st.container(horizontal=True, vertical_alignment="center"):
        ui.status_badge(manifest.status_enum)
        st.markdown(f"**{manifest.run_id}**")
        st.caption(manifest.environment)

    cols = st.columns(4)
    cols[0].metric("Status", manifest.status.replace("_", " "))
    cols[1].metric("Elapsed", ui.format_duration(manifest.duration_seconds))
    cols[2].metric("Started", ui.format_timestamp(manifest.started_at))
    cols[3].metric("Finished", ui.format_timestamp(manifest.ended_at))

    if manifest.status_enum is RunStatus.RUNNING:
        pids = run.active_pids()
        with st.container(horizontal=True, vertical_alignment="center"):
            if st.button("Stop this run", icon=":material/stop_circle:", type="primary", key="stop_live"):
                registry.stop(manifest.run_id)
                st.rerun()
            st.caption(
                f"Interrupts only this run's process tree (pids {pids or '-'}). Locust is "
                "interrupted gracefully first so it still writes its CSV/HTML report."
            )
        if run.stop_requested:
            st.warning("Stop requested -- waiting for the process tree to exit.", icon=":material/hourglass_top:")

    ui.log_view(run.tail(settings.log_tail_lines), key=f"log-{manifest.run_id}")

    if manifest.status_enum.is_terminal:
        st.caption(f"Finished with exit code {manifest.exit_code}.")
        with st.container(horizontal=True):
            if st.button("Review results", icon=":material/analytics:", key="to_results"):
                app_state.set_selected_run(manifest.run_id)
                st.switch_page("app_pages/results.py")


live_panel()

with st.expander("Commands executed (redacted)", icon=":material/code:"):
    for command in run.manifest.redacted_commands or [run.manifest.redacted_command]:
        st.code(command, language="bash", wrap_lines=True)
    st.caption(f"Environment variables supplied: {', '.join(run.manifest.env_keys) or 'none'}")

"""BIC/IRIS load-testing control centre -- Streamlit entry point.

Start it with:

    .venv\\Scripts\\streamlit.exe run streamlit_app.py

Everything the repository previously did through PowerShell -- Locust profiles,
Playwright specs, Databricks OAuth U2M sign-in, report opening -- is available
here. The UI is thin: all logic lives in ``control_centre/``.
"""

from __future__ import annotations

import streamlit as st

import app_state

st.set_page_config(
    page_title="BIC load-testing control centre",
    page_icon=":material/speed:",
    layout="wide",
    initial_sidebar_state="expanded",
)

app_state.init_state()
registry = app_state.get_registry()

pages = {
    "": [
        st.Page("app_pages/dashboard.py", title="Dashboard", icon=":material/dashboard:", default=True),
    ],
    "Set up": [
        st.Page("app_pages/configure.py", title="Configure test", icon=":material/tune:"),
        st.Page("app_pages/authentication.py", title="Authentication", icon=":material/key:"),
    ],
    "Execute": [
        st.Page("app_pages/run_test.py", title="Run test", icon=":material/play_arrow:"),
        st.Page("app_pages/live_logs.py", title="Live logs", icon=":material/terminal:"),
    ],
    "Review": [
        st.Page("app_pages/results.py", title="Results", icon=":material/analytics:"),
        st.Page("app_pages/diagnosis.py", title="AI diagnosis", icon=":material/psychology:"),
        st.Page("app_pages/history.py", title="Run history", icon=":material/history:"),
    ],
    "Reference": [
        st.Page("app_pages/help.py", title="Help & settings", icon=":material/help:"),
    ],
}

page = st.navigation(pages, position="sidebar")

with st.sidebar:
    active = registry.active_runs()
    if active:
        run = active[0]
        st.badge("Run in progress", icon=":material/play_circle:", color="blue")
        st.caption(run.manifest.run_id)
        if st.button("Stop run", icon=":material/stop_circle:", type="primary", width="stretch"):
            registry.stop(run.manifest.run_id)
            st.rerun()
    else:
        st.badge("Idle", icon=":material/pause_circle:", color="gray")

    bundle = app_state.token()
    if bundle is None:
        st.caption("Not authenticated")
    elif bundle.is_expired:
        st.caption(f"Token expired ({bundle.source})")
    else:
        remaining = bundle.expires_in_seconds
        suffix = f" -- {remaining // 60} min left" if remaining is not None else ""
        st.caption(f"Authenticated ({bundle.source}){suffix}")

    st.caption("Local runner. Targets may be deployed services.")

page.run()

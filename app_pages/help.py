"""Help and settings: what each test proves, guardrails, and troubleshooting."""

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
from control_centre.paths import PROJECT_ROOT, relative_to_root
from control_centre.settings import Guardrails

settings = app_state.settings()

st.title("Help & settings", icon=":material/help:")

concepts, discovery, guardrails_tab, trouble = st.tabs(
    ["What the tests prove", "What was discovered", "Guardrails", "Troubleshooting"],
)

with concepts:
    st.subheader("Two tools, two different questions", icon=":material/help:")
    st.markdown(
        """
**Locust** generates concurrent HTTP traffic. It answers *how much load can this API take, and
how slow does it get?* It never renders a page, so it cannot tell you whether the product is
usable.

**Playwright** drives a real Chromium browser through the real React app. It answers *does the
user journey actually work?* It runs one journey at a time, so it tells you nothing about
throughput.

They are complementary, which is why the combined run exists: Locust supplies the load, and one
Playwright journey runs inside that window to show whether the UI stayed usable while the API
was busy.
"""
    )

    st.subheader("Which layers each area covers", icon=":material/layers:")
    st.table(
        [
            {
                "Area": "FastAPI BFF (local)",
                "Included": "FastAPI BFF and everything it calls",
                "Excluded": "React UI, Databricks Apps proxy, auth",
            },
            {
                "Area": "FastAPI BFF (deployed)",
                "Included": "Databricks Apps proxy, BFF, agent, downstream data",
                "Excluded": "React UI",
            },
            {
                "Area": "Serving endpoint",
                "Included": "Model Serving, agent orchestrator, its downstream dependencies",
                "Excluded": "React UI, FastAPI BFF, Apps proxy",
            },
            {
                "Area": "React UI",
                "Included": "Browser, React app, the BFF calls the page makes",
                "Excluded": "Concurrency -- one journey is one user",
            },
            {
                "Area": "Combined",
                "Included": "All of the above at the same time",
                "Excluded": "Multiple real browsers",
            },
        ]
    )

    st.subheader("Things worth knowing", icon=":material/info:")
    st.markdown(
        """
- **The runner is local, the targets usually are not.** Locust and Playwright both run on this
  machine; they point at a deployed Databricks App or serving endpoint. Network latency between
  your machine and the workspace is included in every number you see.
- **Many virtual users, one identity.** Every Locust virtual user shares the single bearer token
  held in this session. That is concurrency under one Databricks principal -- it does not
  exercise per-user isolation, per-user rate limits, or anything that varies by identity.
- **Small samples do not have percentiles.** A one-user, ten-second smoke run produces one or two
  measurements. Locust still prints p90/p95/p99 columns; they are the same number rounded.
- **Playwright and Locust authenticate differently.** Playwright reuses a saved browser session;
  Locust sends a bearer token. Either can expire without the other noticing.
- **Direct serving-endpoint tests skip React and the BFF** but still exercise the agent
  orchestrator and everything downstream of it -- useful for deciding which layer is slow.
"""
    )

with discovery:
    st.subheader("Locust profiles", icon=":material/settings_applications:")
    st.caption(
        "Discovered by scanning the repository root for locust.conf and config/ for *.conf. "
        "Add a file there and it appears here -- no code change needed."
    )
    profiles = discover_locust_profiles()
    st.dataframe(
        [
            {
                "Profile": p.name,
                "File": relative_to_root(p.path),
                "Scenario": p.locustfile,
                "Host": p.host,
                "Users": p.users,
                "Area": p.area.label,
            }
            for p in profiles
        ],
        hide_index=True,
    )

    st.subheader("Locust scenarios", icon=":material/code:")
    st.caption(
        "Discovered from scenarios/*.py. Required and optional environment variables are read "
        "out of the source (_require_env(...) and os.getenv(...)), not hard-coded in this app."
    )
    st.dataframe(
        [
            {
                "Scenario": s.name,
                "Required env": ", ".join(s.required_env) or "-",
                "Optional env": ", ".join(s.optional_env) or "-",
            }
            for s in discover_locust_scenarios()
        ],
        hide_index=True,
    )

    st.subheader("Playwright specs", icon=":material/web:")
    st.caption("Discovered from tests/*.spec.ts, with each file's test titles.")
    st.dataframe(
        [
            {
                "Spec": t.name,
                "Tests": ", ".join(t.titles) or "-",
                "Note": "raw codegen recording" if t.is_recorded_draft else "",
            }
            for t in discover_playwright_tests()
        ],
        hide_index=True,
    )

    if st.button("Rescan repository", icon=":material/refresh:"):
        refresh_all()
        st.rerun()

    st.subheader("Adding your own", icon=":material/add:")
    st.markdown(
        f"""
**A new Locust profile:** drop a `.conf` file in `{relative_to_root(PROJECT_ROOT / 'config')}/`
named `locust.<name>.conf` with `locustfile`, `host`, `users`, `spawn-rate`, `run-time`,
`headless`, `csv` and `html` keys, then rescan. Or configure a run here and use
**Save these Locust values as a new profile** on the Configure page.

**A new Locust scenario:** add `scenarios/<name>.py` that subclasses `TokenAuthHttpUser` from
`scenarios/auth.py`. Use `_require_env("X")` for variables the scenario cannot run without and
`os.getenv("X", default)` for optional ones -- this app reads those calls to build its form.

**A new Playwright spec:** add `tests/<name>.spec.ts`. Use the configured `baseURL` and the
global `storageState` rather than hard-coding either, so the control centre can retarget it.
"""
    )

with guardrails_tab:
    st.subheader("Operational limits", icon=":material/shield:")
    st.caption(
        "Hard ceilings the UI refuses to exceed regardless of what a profile file says. "
        "Stress profiles additionally require a typed confirmation and are never started on startup."
    )
    row = st.columns(3)
    max_users = int(
        row[0].number_input("Max users", 1, 1000, settings.guardrails.max_users, key="g_users")
    )
    max_spawn = float(
        row[1].number_input("Max spawn rate", 0.1, 200.0, settings.guardrails.max_spawn_rate, key="g_spawn")
    )
    max_runtime = int(
        row[2].number_input(
            "Max run time (seconds)", 10, 86_400, settings.guardrails.max_run_time_seconds, key="g_runtime"
        )
    )
    row2 = st.columns(3)
    stress_threshold = int(
        row2[0].number_input(
            "Stress confirmation above N users", 1, 100, settings.guardrails.stress_user_threshold, key="g_stress"
        )
    )
    max_workers = int(
        row2[1].number_input(
            "Max Playwright workers", 1, 32, settings.guardrails.max_playwright_workers, key="g_workers"
        )
    )
    max_repeat = int(
        row2[2].number_input("Max repeat-each", 1, 100, settings.guardrails.max_repeat_each, key="g_repeat")
    )

    st.subheader("Defaults", icon=":material/tune:")
    d1 = st.text_input("Default workspace host", settings.default_workspace_host, key="g_ws")
    d2 = st.text_input("Default app host", settings.default_app_host, key="g_app")
    d3 = st.text_input("Default serving endpoint", settings.default_serving_endpoint, key="g_ep")
    markers = st.text_input(
        "Production host markers (comma separated)",
        ", ".join(settings.production_host_markers),
        key="g_markers",
        help="A target whose host contains any of these shows a production reminder.",
    )
    refresh_seconds = int(
        st.number_input("Live-log refresh (seconds)", 1, 30, settings.auto_refresh_seconds, key="g_refresh")
    )

    if st.button("Save settings", icon=":material/save:", type="primary"):
        settings.guardrails = Guardrails(
            max_users=max_users,
            max_spawn_rate=max_spawn,
            max_run_time_seconds=max_runtime,
            max_playwright_workers=max_workers,
            max_repeat_each=max_repeat,
            stress_user_threshold=stress_threshold,
        )
        settings.default_workspace_host = d1.strip()
        settings.default_app_host = d2.strip()
        settings.default_serving_endpoint = d3.strip()
        settings.production_host_markers = [m.strip() for m in markers.split(",") if m.strip()]
        settings.auto_refresh_seconds = refresh_seconds
        app_state.save_settings(settings)
        st.success("Saved to config/app-settings.json.", icon=":material/check_circle:")

    st.subheader("Secret handling", icon=":material/lock:")
    st.markdown(
        """
- Tokens live in this Streamlit session's memory and nowhere else.
- They are passed to a test only through that subprocess's `env`, never as a command-line argument.
- Logs, command previews and run manifests are passed through a redaction filter that masks
  bearer headers, Databricks PATs, JWT-shaped strings and any registered literal value.
- `playwright/.auth/bic-user.json` is never displayed; only counts and timestamps are shown.
- Result and report paths are validated to stay inside `results/`, so a crafted path cannot read
  or write elsewhere.
- There is no free-form shell-command field anywhere in this app.
"""
    )

with trouble:
    st.subheader("Common problems", icon=":material/troubleshoot:")
    st.markdown(
        """
**401 from the deployed app or the serving endpoint.** The held token is missing or expired.
Go to Authentication, run step 2 again, then restart the run. Unlike the PowerShell script, the
token is obtained by this process, so there is no "wrong window" problem.

**Playwright fails or redirects to a login page.** The saved browser session expired. Capture a
new one on the Authentication tab, then re-run the UI smoke spec.

**`npx` or `node` not found in preflight.** Node.js is not on this server's PATH. Install it and
restart Streamlit -- the toolchain probe is cached for ten minutes.

**Chromium missing.** Run `npx playwright install chromium` in the project folder.

**A run shows "cancelled" right after starting.** Something interrupted the process tree. Check
the run log; Locust and Playwright both write their reason to stdout.

**Locust reports 0 requests.** The scenario raised during startup -- usually a required
environment variable was empty. The run log shows the exact `RuntimeError`.

**The report will not embed.** Locust's HTML is one self-contained file and embeds fine;
Playwright's is a directory, so use **Launch playwright show-report** or download the zip.

**Stopping a run did not produce a report.** A hard kill skips the report. The stop button
interrupts gracefully first and waits up to 20 seconds before escalating.
"""
    )

    st.subheader("Where things live", icon=":material/folder_open:")
    st.code(
        """streamlit_app.py        entry point and navigation
app_state.py            session state, registry, cached toolchain probes
ui_components.py        shared Streamlit fragments
app_pages/              one file per page
control_centre/         all backend logic (importable without Streamlit)
  paths.py              project paths and containment rules
  settings.py           guardrails, thresholds, diagnosis config
  discovery.py          profile / scenario / spec discovery
  validation.py         URL, numeric, duration and path validation
  auth.py               Databricks CLI OAuth, PAT, storage-state inspection
  commands.py           argv construction and subprocess env
  process.py            background execution, log streaming, safe stop
  orchestrator.py       config -> manifest -> launched run
  runs.py               run ids, result directories, manifests
  locust_results.py     CSV parsing
  playwright_results.py JSON report parsing
  reports.py            opening, zipping and downloading reports
  diagnosis.py          LLM diagnosis adapter
  preflight.py          toolchain and run-specific checks
  redaction.py          secret masking""",
        language="text",
    )

    st.caption(f"Project root: {PROJECT_ROOT}")
    ui.check_list(app_state.cached_toolchain_checks(), title="Current toolchain")

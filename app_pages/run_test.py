"""Run test: review the resolved configuration, pass preflight, then start."""

from __future__ import annotations

import streamlit as st

import app_state
import ui_components as ui
from control_centre.commands import build_locust_argv, build_playwright_argv
from control_centre.models import AuthMethod, CombinedRunConfig, LocustRunConfig, PlaywrightRunConfig
from control_centre.orchestrator import (
    busy_output_paths,
    start_combined_run,
    start_locust_run,
    start_playwright_run,
)
from control_centre.preflight import (
    Check,
    check_file_exists,
    check_output_free,
    check_results_writable,
)
from control_centre.redaction import preview_command
from control_centre.validation import (
    requires_stress_confirmation,
    validate_combined_config,
    validate_locust_config,
    validate_playwright_config,
)

settings = app_state.settings()
registry = app_state.get_registry()
area = app_state.area()

st.title("Run test", icon=":material/play_arrow:")

draft = app_state.draft_for_area()
if draft is None:
    st.info("Nothing configured yet for this area.", icon=":material/info:")
    if st.button("Go to Configure test", icon=":material/tune:", type="primary"):
        st.switch_page("app_pages/configure.py")
    st.stop()

active = registry.active_runs()

# --------------------------------------------------------------------------
# Resolved configuration
# --------------------------------------------------------------------------
st.subheader("Resolved configuration", icon=":material/fact_check:")

if isinstance(draft, CombinedRunConfig):
    host = draft.locust.host
    ui.target_banner(host, settings, label="Load + UI target")
    cols = st.columns(4)
    cols[0].metric("Users", draft.locust.users, border=True)
    cols[1].metric("Run time", draft.locust.run_time, border=True)
    cols[2].metric("Warm-up", f"{draft.warmup_seconds}s", border=True)
    cols[3].metric("UI spec", draft.playwright.test_file.split("/")[-1], border=True)
    commands = [
        preview_command(build_locust_argv(draft.locust)),
        preview_command(build_playwright_argv(draft.playwright)),
    ]
elif isinstance(draft, PlaywrightRunConfig):
    host = draft.base_url
    ui.target_banner(host, settings, label="UI target")
    cols = st.columns(4)
    cols[0].metric("Spec", draft.test_file.split("/")[-1], border=True)
    cols[1].metric("Workers", draft.workers, border=True)
    cols[2].metric("repeat-each", draft.repeat_each, border=True)
    cols[3].metric("Mode", "headed" if draft.headed else "headless", border=True)
    commands = [preview_command(build_playwright_argv(draft))]
else:
    assert isinstance(draft, LocustRunConfig)
    host = draft.host
    ui.target_banner(host, settings)
    cols = st.columns(4)
    cols[0].metric("Scenario", draft.locustfile.split("/")[-1], border=True)
    cols[1].metric("Users", draft.users, border=True)
    cols[2].metric("Spawn rate", f"{draft.spawn_rate:g}/s", border=True)
    cols[3].metric("Run time", draft.run_time, border=True)
    commands = [preview_command(build_locust_argv(draft))]

with st.expander("Full resolved configuration", icon=":material/data_object:"):
    st.json(draft.to_manifest())

ui.command_preview(commands)

# --------------------------------------------------------------------------
# Validation + preflight
# --------------------------------------------------------------------------
st.subheader("Preflight", icon=":material/checklist:")

if isinstance(draft, CombinedRunConfig):
    storage = app_state.storage_state(draft.playwright.base_url)
elif isinstance(draft, PlaywrightRunConfig):
    storage = app_state.storage_state(draft.base_url)
else:
    storage = app_state.storage_state()
auth_available = app_state.has_usable_token()

if isinstance(draft, CombinedRunConfig):
    validation = validate_combined_config(
        draft,
        settings,
        auth_available=auth_available,
        storage_state_exists=storage.exists,
        storage_state_problem=storage.problem,
    )
    output_paths = [
        draft.locust.csv_prefix,
        draft.locust.html_path,
        draft.playwright.html_report_dir,
    ]
    file_checks = [
        check_file_exists("Locust scenario", draft.locust.locustfile),
        check_file_exists("Playwright spec", draft.playwright.test_file),
    ]
elif isinstance(draft, PlaywrightRunConfig):
    validation = validate_playwright_config(
        draft, settings, storage_state_exists=storage.exists, storage_state_problem=storage.problem
    )
    output_paths = [draft.html_report_dir, draft.json_report_path]
    file_checks = [check_file_exists("Playwright spec", draft.test_file)]
else:
    validation = validate_locust_config(
        draft, settings, auth_available=auth_available, available_env=set()
    )
    output_paths = [draft.csv_prefix, draft.html_path]
    file_checks = [check_file_exists("Locust scenario", draft.locustfile)]

toolchain = app_state.cached_toolchain_checks()
needs_node = isinstance(draft, (PlaywrightRunConfig, CombinedRunConfig))
relevant_tools = [
    c
    for c in toolchain
    if needs_node or c.name in {"Python", "Locust", "Databricks CLI", "Results directory"}
]

auth_check = Check(
    "Authentication",
    auth_available or app_state.auth_method() is AuthMethod.NONE,
    app_state.auth_method().label if auth_available else "no token held",
    "Authenticate on the Authentication page, or select no-auth mode for a local target.",
    required=False,
)
checks = [
    *relevant_tools,
    *file_checks,
    check_results_writable(),
    check_output_free(output_paths, busy_output_paths(registry)),
    auth_check,
]
preflight_ok = ui.check_list(checks)
config_ok = ui.validation_report(validation)

if isinstance(draft, LocustRunConfig) and not draft.headless:
    st.warning(
        "Headless is off: Locust will start its own web UI and will not stop on its own or "
        "write a report. Turn headless back on for an unattended run.",
        icon=":material/warning:",
    )

# --------------------------------------------------------------------------
# Stress confirmation
# --------------------------------------------------------------------------
locust_part = (
    draft.locust if isinstance(draft, CombinedRunConfig) else draft if isinstance(draft, LocustRunConfig) else None
)
stress_ok = True
if locust_part is not None and requires_stress_confirmation(locust_part, settings):
    st.subheader("Stress confirmation required", icon=":material/priority_high:")
    st.warning(
        f"This profile runs **{locust_part.users} concurrent users** against `{locust_part.host}` "
        f"for {locust_part.run_time}. Smoke profiles are one user; anything above "
        f"{settings.guardrails.stress_user_threshold} is treated as a stress test.",
        icon=":material/warning:",
    )
    typed = st.text_input(
        "Type RUN STRESS to confirm",
        value="",
        key="stress_confirm",
        help="Deliberate friction: stress profiles are never started by accident or on app startup.",
    )
    stress_ok = typed.strip().upper() == "RUN STRESS"

# --------------------------------------------------------------------------
# Start / stop
# --------------------------------------------------------------------------
st.subheader("Execute", icon=":material/bolt:")

if active:
    run = active[0]
    st.info(
        f"Run `{run.manifest.run_id}` is already in progress. Only one run at a time is allowed, "
        "so results and reports cannot collide.",
        icon=":material/info:",
    )
    with st.container(horizontal=True):
        if st.button("Open live logs", icon=":material/terminal:", type="primary"):
            st.switch_page("app_pages/live_logs.py")
        if st.button("Stop that run", icon=":material/stop_circle:"):
            registry.stop(run.manifest.run_id)
            st.rerun()
else:
    can_run = preflight_ok and config_ok and stress_ok
    if st.button(
        "Start run",
        icon=":material/play_arrow:",
        type="primary",
        disabled=not can_run,
    ):
        token = app_state.token()
        method = app_state.auth_method()
        try:
            if isinstance(draft, CombinedRunConfig):
                run = start_combined_run(
                    registry, draft, token=token, auth_method=method, settings=settings
                )
            elif isinstance(draft, PlaywrightRunConfig):
                run = start_playwright_run(registry, draft, settings=settings)
            else:
                run = start_locust_run(
                    registry, draft, area=area, token=token, auth_method=method, settings=settings
                )
        except RuntimeError as exc:
            st.error(str(exc), icon=":material/error:")
        else:
            app_state.remember_active_run(run.manifest.run_id)
            st.toast(f"Started {run.manifest.run_id}", icon=":material/play_arrow:")
            st.switch_page("app_pages/live_logs.py")
    if not can_run:
        st.caption("Resolve the blocking preflight and validation items above to enable Run.")

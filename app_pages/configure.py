"""Configure test: pick what to test, pick a profile, review and override safely.

Defaults always come from the repository's own ``.conf`` files and specs. Edits
made here apply to this run only -- the source profile is never modified unless
the user explicitly saves a new one.
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

import app_state
import ui_components as ui
from control_centre.discovery import (
    discover_locust_profiles,
    discover_locust_scenarios,
    discover_playwright_tests,
    find_scenario,
    scenario_env_requirements,
)
from control_centre.models import (
    CombinedRunConfig,
    LocustProfile,
    LocustRunConfig,
    PlaywrightRunConfig,
    TestArea,
)
from control_centre.orchestrator import locust_config_from_profile, playwright_config_default
from control_centre.paths import CONFIG_DIR, PLAYWRIGHT_STORAGE_STATE, relative_to_root
from control_centre.validation import (
    SCREENSHOT_CHOICES,
    TRACE_CHOICES,
    VIDEO_CHOICES,
    validate_serving_endpoint,
)

settings = app_state.settings()
PLACEHOLDER_RUN_ID = "<run-id>"

AREA_HELP = {
    TestArea.BFF: (
        "**Included:** the FastAPI BFF and, for a deployed target, the Databricks Apps "
        "proxy in front of it, plus everything the BFF calls.\n\n"
        "**Excluded:** the React UI -- no browser is involved.\n\n"
        "Measures API throughput and latency under concurrency."
    ),
    TestArea.UI: (
        "**Included:** the real React app in Chromium -- rendering, session creation, "
        "the streaming answer, and the BFF calls the page makes.\n\n"
        "**Excluded:** concurrency. One browser journey is one user.\n\n"
        "Measures whether the product is actually usable, which a 200 response cannot prove."
    ),
    TestArea.SERVING: (
        "**Included:** the Databricks Model Serving endpoint and the agent orchestrator "
        "behind it, including its downstream dependencies (Genie/SQL, model calls).\n\n"
        "**Excluded:** React and the FastAPI BFF entirely.\n\n"
        "Use it to decide whether a slow or failing chat is the agent's fault or the BFF's."
    ),
    TestArea.COMBINED: (
        "Locust drives API load while one Playwright journey runs through the real UI "
        "against the same deployed app.\n\n"
        "Answers the question neither tool answers alone: *does the UI stay usable while "
        "the API is under load?*"
    ),
}

st.title("Configure test", icon=":material/tune:")

area_options = [TestArea.BFF, TestArea.UI, TestArea.SERVING, TestArea.COMBINED]
current = st.segmented_control(
    "What do you want to test?",
    area_options,
    format_func=lambda a: a.label,
    default=app_state.area(),
    key="area_select",
)
if current is None:
    current = app_state.area()
app_state.set_area(current)
st.caption(AREA_HELP[current].split("\n\n")[0])
with st.expander("What this covers and excludes", icon=":material/info:"):
    st.markdown(AREA_HELP[current])

profiles = discover_locust_profiles()
scenarios = discover_locust_scenarios()
tests = discover_playwright_tests()


# --------------------------------------------------------------------------
# Shared editors
# --------------------------------------------------------------------------


def _profile_options(area: TestArea) -> list[LocustProfile]:
    preferred = [p for p in profiles if p.area is area]
    return preferred + [p for p in profiles if p.area is not area]


def _env_editor(locustfile: str, key_prefix: str) -> dict[str, str]:
    """Render inputs for exactly the env vars the selected scenario reads."""
    required, optional = scenario_env_requirements(locustfile)
    interesting = [name for name in (*required, *optional) if name != "BIC_AUTH_TOKEN"]
    values: dict[str, str] = {}
    if not interesting:
        st.caption("This scenario needs no extra environment variables.")
        return values

    for name in interesting:
        is_required = name in required
        label = f"{name}{' (required)' if is_required else ''}"
        widget_key = f"{key_prefix}:{name}"
        if name == "BIC_ENABLE_FULL_FLOW":
            enabled = st.toggle(
                "Run the full stateful chat flow",
                value=True,
                key=widget_key,
                help="Off runs only the read-only checks (health, healthz, me, data-sources).",
            )
            values[name] = "true" if enabled else "false"
        elif name == "BIC_REQUEST_TIMEOUT_SECONDS":
            values[name] = str(
                st.number_input(
                    "Request timeout (seconds)",
                    min_value=5,
                    max_value=900,
                    value=180,
                    step=5,
                    key=widget_key,
                )
            )
        elif name == "BIC_SERVING_ENDPOINT_PATH":
            raw = st.text_input(
                "Serving endpoint (name or full path)",
                value=settings.default_serving_endpoint,
                key=widget_key,
                help="Either 'my-endpoint' or '/serving-endpoints/my-endpoint/invocations'.",
            )
            from control_centre.models import ValidationResult

            probe = ValidationResult()
            normalised = validate_serving_endpoint(raw, "serving_endpoint", probe)
            if probe.errors:
                st.error(probe.errors[0].message, icon=":material/error:")
            else:
                st.caption(f"Resolved path: `{normalised}`")
                values[name] = normalised
        elif name == "BIC_TEST_QUESTION":
            values[name] = st.text_input(
                "Test question", value="Hello", key=widget_key, help="Sent as the user turn."
            )
        elif name == "BIC_TEST_USER_ID":
            values[name] = st.text_input(
                label,
                value="",
                key=widget_key,
                placeholder="first.last@company.com",
                help="Your Databricks user id/email, forwarded in custom_inputs.user_id.",
            )
        elif name == "BIC_SESSION_ID_PREFIX":
            values[name] = st.text_input(
                "Session id prefix",
                value="load_test",
                key=widget_key,
                help="A unique session id is generated per invocation as <prefix>_<uuid4>.",
            )
            st.caption("Session ids are always uniquely generated per request; only the prefix is configurable.")
        else:
            values[name] = st.text_input(label, value="", key=widget_key)
    return {k: v for k, v in values.items() if v != ""}


def _locust_editor(profile: LocustProfile, key_prefix: str) -> LocustRunConfig:
    """Editable copy of a profile's values; the file on disk is untouched."""
    defaults = locust_config_from_profile(profile, "00000000-000000-fastapi_bff-000000")
    scenario_names = [s.name for s in scenarios]
    default_scenario = Path(defaults.locustfile).name
    index = scenario_names.index(default_scenario) if default_scenario in scenario_names else 0

    scenario_name = st.selectbox(
        "Locust scenario",
        scenario_names,
        index=index,
        key=f"{key_prefix}:scenario",
        help="Discovered from scenarios/*.py.",
    )
    scenario = find_scenario(scenario_name)
    if scenario is not None and scenario.summary:
        st.caption(scenario.summary[:280])

    host = st.text_input("Host", value=defaults.host, key=f"{key_prefix}:host")

    row = st.columns(3)
    users = row[0].number_input(
        "Users",
        min_value=1,
        max_value=settings.guardrails.max_users,
        value=min(defaults.users, settings.guardrails.max_users),
        key=f"{key_prefix}:users",
    )
    spawn_rate = row[1].number_input(
        "Spawn rate (users/s)",
        min_value=0.1,
        max_value=float(settings.guardrails.max_spawn_rate),
        value=min(float(defaults.spawn_rate), float(settings.guardrails.max_spawn_rate)),
        step=0.5,
        key=f"{key_prefix}:spawn",
    )
    run_time = row[2].text_input(
        "Run time", value=defaults.run_time, key=f"{key_prefix}:runtime", help="e.g. 10s, 2m, 1h30m"
    )

    headless = st.toggle(
        "Headless (no Locust web UI)",
        value=defaults.headless,
        key=f"{key_prefix}:headless",
        help="Headless is required for an unattended run that writes CSV/HTML output.",
    )

    st.markdown("**Scenario environment**")
    extra_env = _env_editor(f"scenarios/{scenario_name}", key_prefix)

    config = LocustRunConfig(
        profile_name=profile.name,
        locustfile=f"scenarios/{scenario_name}",
        host=host.strip(),
        users=int(users),
        spawn_rate=float(spawn_rate),
        run_time=run_time.strip(),
        headless=bool(headless),
        csv_prefix=f"results/{PLACEHOLDER_RUN_ID}/locust",
        html_path=f"results/{PLACEHOLDER_RUN_ID}/locust.html",
        extra_env=extra_env,
    )

    with st.expander("Advanced -- output locations", icon=":material/folder_open:"):
        st.caption(
            "By default every run writes to its own results/<run-id>/ directory, so earlier "
            "results are never overwritten."
        )
        override = st.toggle("Override output paths", value=False, key=f"{key_prefix}:override")
        if override:
            config.custom_outputs = True
            config.csv_prefix = st.text_input(
                "CSV prefix", value="results/manual/locust", key=f"{key_prefix}:csv"
            )
            config.html_path = st.text_input(
                "HTML report", value="results/manual/locust.html", key=f"{key_prefix}:html"
            )
            st.caption("Paths must stay inside results/.")
    return config


def _playwright_editor(key_prefix: str, default_base_url: str) -> PlaywrightRunConfig:
    spec_names = [t.name for t in tests]
    if not spec_names:
        st.error("No Playwright specs found under tests/.", icon=":material/error:")
        st.stop()

    preferred = "bic-smoke.spec.ts" if "bic-smoke.spec.ts" in spec_names else spec_names[0]
    chosen = st.selectbox(
        "Playwright spec",
        spec_names,
        index=spec_names.index(preferred),
        key=f"{key_prefix}:spec",
        help="Discovered from tests/*.spec.ts.",
    )
    spec = next(t for t in tests if t.name == chosen)
    st.caption(f"Test: {spec.summary}")
    if spec.is_recorded_draft:
        st.warning(
            "This is a raw Codegen recording with a hard-coded absolute auth path and no "
            "assertions. Useful as a reference, not as a check.",
            icon=":material/warning:",
        )

    config = playwright_config_default(
        f"tests/{chosen}", PLACEHOLDER_RUN_ID, default_base_url, relative_to_root(PLAYWRIGHT_STORAGE_STATE)
    )

    row = st.columns(3)
    config.project = row[0].text_input("Project", value="chromium", key=f"{key_prefix}:project")
    config.workers = int(
        row[1].number_input(
            "Workers",
            min_value=1,
            max_value=settings.guardrails.max_playwright_workers,
            value=1,
            key=f"{key_prefix}:workers",
        )
    )
    config.repeat_each = int(
        row[2].number_input(
            "repeat-each",
            min_value=1,
            max_value=settings.guardrails.max_repeat_each,
            value=1,
            key=f"{key_prefix}:repeat",
            help="3 runs the same journey three times -- the documented repeatability check.",
        )
    )

    config.base_url = st.text_input("Base URL", value=default_base_url, key=f"{key_prefix}:baseurl").strip()
    row2 = st.columns(2)
    config.headed = row2[0].toggle(
        "Headed (visible browser)",
        value=False,
        key=f"{key_prefix}:headed",
        help="Use for a live demo. Headless is the default for automated runs.",
    )
    config.timeout_ms = int(
        row2[1].number_input(
            "Test timeout (ms)",
            min_value=1000,
            max_value=1_800_000,
            value=120_000,
            step=10_000,
            key=f"{key_prefix}:timeout",
        )
    )

    storage = app_state.storage_state(config.base_url)
    with st.container(border=True):
        st.caption("Saved authentication state")
        st.markdown(f"`{relative_to_root(PLAYWRIGHT_STORAGE_STATE)}` -- **{storage.status_text}**")
        if storage.problem:
            st.caption(storage.problem)
        st.caption("Contents are never displayed. Regenerate it on the Authentication page.")

    with st.expander("Advanced -- artefacts and filtering", icon=":material/settings:"):
        arow = st.columns(3)
        config.trace = arow[0].selectbox(
            "Trace", TRACE_CHOICES, index=TRACE_CHOICES.index("retain-on-failure"), key=f"{key_prefix}:trace"
        )
        config.screenshot = arow[1].selectbox(
            "Screenshot",
            SCREENSHOT_CHOICES,
            index=SCREENSHOT_CHOICES.index("only-on-failure"),
            key=f"{key_prefix}:shot",
        )
        config.video = arow[2].selectbox(
            "Video", VIDEO_CHOICES, index=VIDEO_CHOICES.index("off"), key=f"{key_prefix}:video"
        )
        config.grep = st.text_input(
            "Only run tests matching (--grep)", value="", key=f"{key_prefix}:grep"
        ).strip()
        st.caption(
            "HTML and JSON reports are always written into this run's own directory. "
            "The JSON report is what the Results and AI diagnosis pages read."
        )
    return config


# --------------------------------------------------------------------------
# Area-specific configuration
# --------------------------------------------------------------------------

if current in (TestArea.BFF, TestArea.SERVING):
    options = _profile_options(current)
    if not options:
        st.error("No Locust .conf profiles found.", icon=":material/error:")
        st.stop()

    labels = {p.name: p.name for p in options}
    chosen_name = st.selectbox(
        "Profile",
        [p.name for p in options],
        format_func=lambda n: labels[n],
        key="locust_profile_choice",
        help="Every .conf file found in the repository root and config/.",
    )
    profile = next(p for p in options if p.name == chosen_name)
    st.caption(profile.description or "No description in the profile file.")
    st.caption(f"Source: `{relative_to_root(profile.path)}` (never modified by this app)")

    config = _locust_editor(profile, f"locust:{profile.name}")
    ui.target_banner(config.host, settings)

    if current is TestArea.SERVING:
        st.info(
            "Direct serving-endpoint testing bypasses React and the FastAPI BFF. It still "
            "exercises the agent orchestrator and its downstream dependencies, so it isolates "
            "agent-layer latency and failures from anything the BFF or UI adds.",
            icon=":material/info:",
        )
        st.caption(
            "Streaming is not offered here: the repository's serving-endpoint scenarios are "
            "non-streaming. Use the stream profiles under FastAPI BFF for SSE timing."
        )

    if st.button("Use this configuration", icon=":material/check:", type="primary"):
        app_state.set_locust_draft(config)
        app_state.set_combined_draft(None)
        st.success("Configuration saved for this session.", icon=":material/check_circle:")
        st.switch_page("app_pages/run_test.py")

elif current is TestArea.UI:
    config = _playwright_editor("pw", settings.default_app_host)
    ui.target_banner(config.base_url, settings, label="UI target")
    st.caption(
        "A Playwright run authenticates with the saved browser session, not with the OAuth "
        "bearer token used by Locust. The two auth paths are independent."
    )
    if st.button("Use this configuration", icon=":material/check:", type="primary"):
        app_state.set_playwright_draft(config)
        app_state.set_combined_draft(None)
        st.success("Configuration saved for this session.", icon=":material/check_circle:")
        st.switch_page("app_pages/run_test.py")

else:  # Combined
    st.markdown("### 1. Load profile")
    options = _profile_options(TestArea.BFF)
    chosen_name = st.selectbox("Locust profile", [p.name for p in options], key="combined_profile")
    profile = next(p for p in options if p.name == chosen_name)
    st.caption(profile.description or "")
    locust_config = _locust_editor(profile, f"combined-locust:{profile.name}")

    st.markdown("### 2. UI journey")
    playwright_config = _playwright_editor("combined-pw", locust_config.host or settings.default_app_host)

    st.markdown("### 3. Orchestration")
    row = st.columns(2)
    warmup = int(
        row[0].number_input(
            "Warm-up before the UI journey (seconds)",
            min_value=0,
            max_value=600,
            value=15,
            step=5,
            key="combined_warmup",
            help="Gives Locust time to reach the configured user count before the browser starts.",
        )
    )
    stop_after = row[1].toggle(
        "Stop Locust when the UI journey finishes",
        value=False,
        key="combined_stop",
        help="Off lets the load run to its configured run time; Locust still writes its report either way.",
    )

    combined = CombinedRunConfig(
        locust=locust_config,
        playwright=playwright_config,
        warmup_seconds=warmup,
        stop_locust_after_ui=bool(stop_after),
    )
    ui.target_banner(locust_config.host, settings, label="Load target")
    if st.button("Use this configuration", icon=":material/check:", type="primary"):
        app_state.set_combined_draft(combined)
        app_state.set_locust_draft(None)
        app_state.set_playwright_draft(None)
        st.success("Combined configuration saved.", icon=":material/check_circle:")
        st.switch_page("app_pages/run_test.py")


# --------------------------------------------------------------------------
# Saving a new profile (explicit, never implicit)
# --------------------------------------------------------------------------

if current in (TestArea.BFF, TestArea.SERVING, TestArea.COMBINED):
    with st.expander("Save these Locust values as a new profile", icon=":material/save:"):
        st.caption(
            "Writes a new .conf file in config/. The profile you started from is never changed."
        )
        draft = app_state.locust_draft() or (
            app_state.combined_draft().locust if app_state.combined_draft() else None
        )
        new_name = st.text_input("Profile name", value="", placeholder="my-smoke", key="save_profile_name")
        if st.button("Save profile", icon=":material/save:", disabled=not new_name or draft is None):
            safe = "".join(ch for ch in new_name if ch.isalnum() or ch in "-_")
            if not safe:
                st.error("Profile name must contain letters, digits, '-' or '_'.", icon=":material/error:")
            else:
                target = CONFIG_DIR / f"locust.{safe}.conf"
                if target.exists():
                    st.error(f"{target.name} already exists.", icon=":material/error:")
                else:
                    assert draft is not None
                    target.write_text(
                        "\n".join(
                            [
                                f"# Saved from the control centre on top of profile '{draft.profile_name}'.",
                                f"locustfile = {draft.locustfile}",
                                f"headless = {'true' if draft.headless else 'false'}",
                                f"users = {draft.users}",
                                f"spawn-rate = {draft.spawn_rate:g}",
                                f"run-time = {draft.run_time}",
                                f"host = {draft.host}",
                                f"csv = results/{safe}",
                                f"html = results/{safe}.html",
                                "",
                            ]
                        ),
                        encoding="utf-8",
                    )
                    st.success(f"Wrote {relative_to_root(target)}.", icon=":material/check_circle:")
                    st.caption("Rescan the repository on the Dashboard to pick it up.")

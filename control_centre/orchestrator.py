"""Glue between a validated configuration and a launched run.

Turns a ``*RunConfig`` into an isolated ``results/<run-id>/`` directory, a run
manifest, and the argv/env of the processes that implement it -- then hands them
to the ``RunRegistry``. This is the only place that knows how the pieces fit
together, which keeps both the Streamlit pages and the process layer simple.
"""

from __future__ import annotations

from dataclasses import asdict

from control_centre.auth import TokenBundle
from control_centre.commands import (
    build_env,
    build_locust_argv,
    build_playwright_argv,
)
from control_centre.models import (
    AuthMethod,
    CombinedRunConfig,
    LocustProfile,
    LocustRunConfig,
    PlaywrightRunConfig,
    TestArea,
)
from control_centre.paths import PLAYWRIGHT_STORAGE_STATE, relative_to_root
from control_centre.process import (
    ManagedRun,
    RunRegistry,
    Step,
    make_combined_supervisor,
    sequential_supervisor,
)
from control_centre.runs import RunManifest, default_artifacts, new_run_id
from control_centre.settings import AppSettings
from control_centre.validation import parse_duration_seconds

# Head-room on top of the configured run time before a run is declared timed out.
LOCUST_TIMEOUT_MARGIN_SECONDS = 180
PLAYWRIGHT_TIMEOUT_MARGIN_SECONDS = 180


# --------------------------------------------------------------------------
# Default configurations
# --------------------------------------------------------------------------


def locust_config_from_profile(profile: LocustProfile, run_id: str) -> LocustRunConfig:
    """Profile defaults, re-pointed at this run's own isolated output directory."""
    values = profile.values
    try:
        spawn_rate = float(values.get("spawn-rate", values.get("spawn_rate", "1")))
    except ValueError:
        spawn_rate = 1.0
    artifacts = default_artifacts(run_id, "locust")
    return LocustRunConfig(
        profile_name=profile.name,
        locustfile=values.get("locustfile", ""),
        host=values.get("host", ""),
        users=profile.users,
        spawn_rate=spawn_rate,
        run_time=values.get("run-time", values.get("run_time", "10s")),
        headless=str(values.get("headless", "true")).lower() != "false",
        csv_prefix=artifacts["locust_csv_prefix"],
        html_path=artifacts["locust_html"],
    )


def playwright_config_default(
    test_file: str, run_id: str, base_url: str, storage_state: str = ""
) -> PlaywrightRunConfig:
    artifacts = default_artifacts(run_id, "playwright")
    return PlaywrightRunConfig(
        test_file=test_file,
        base_url=base_url,
        storage_state=storage_state or relative_to_root(PLAYWRIGHT_STORAGE_STATE),
        html_report_dir=artifacts["playwright_html_dir"],
        json_report_path=artifacts["playwright_json"],
        output_dir=artifacts["playwright_output_dir"],
    )


def repoint_locust_outputs(config: LocustRunConfig, run_id: str) -> LocustRunConfig:
    """Point output at this run's own directory unless the user overrode it."""
    if config.custom_outputs:
        return config
    artifacts = default_artifacts(run_id, "locust")
    config.csv_prefix = artifacts["locust_csv_prefix"]
    config.html_path = artifacts["locust_html"]
    return config


def repoint_playwright_outputs(config: PlaywrightRunConfig, run_id: str) -> PlaywrightRunConfig:
    if config.custom_outputs:
        return config
    artifacts = default_artifacts(run_id, "playwright")
    config.html_report_dir = artifacts["playwright_html_dir"]
    config.json_report_path = artifacts["playwright_json"]
    config.output_dir = artifacts["playwright_output_dir"]
    return config


# --------------------------------------------------------------------------
# Timeouts
# --------------------------------------------------------------------------


def locust_timeout(config: LocustRunConfig) -> int:
    seconds = parse_duration_seconds(config.run_time) or 60
    return seconds + LOCUST_TIMEOUT_MARGIN_SECONDS


def playwright_timeout(config: PlaywrightRunConfig) -> int:
    per_test = config.timeout_ms / 1000.0
    return int(per_test * max(1, config.repeat_each) + PLAYWRIGHT_TIMEOUT_MARGIN_SECONDS)


# --------------------------------------------------------------------------
# Launching
# --------------------------------------------------------------------------


def _manifest(
    run_id: str,
    area: TestArea,
    kind: str,
    *,
    profile: str,
    environment: str,
    config: dict,
    auth_method: AuthMethod,
    env_keys: list[str],
    label: str = "",
    notes: list[str] | None = None,
) -> RunManifest:
    return RunManifest(
        run_id=run_id,
        area=area.value,
        kind=kind,
        label=label,
        profile=profile,
        environment=environment,
        config=config,
        auth_method=auth_method.value,
        env_keys=sorted(env_keys),
        artifacts=default_artifacts(run_id, kind),
        notes=list(notes or []),
    )


def start_locust_run(
    registry: RunRegistry,
    config: LocustRunConfig,
    *,
    area: TestArea,
    token: TokenBundle | None,
    auth_method: AuthMethod,
    settings: AppSettings,
    run_id: str | None = None,
    label: str = "",
) -> ManagedRun:
    run_id = run_id or new_run_id(area)
    repoint_locust_outputs(config, run_id)
    argv = build_locust_argv(config)
    env = build_env(token=token, extra=config.extra_env)

    notes: list[str] = []
    if token is not None:
        notes.append("Load generated under a single Databricks identity (one bearer token).")
    if settings.is_production_host(config.host):
        notes.append("Target host matched a production marker.")

    manifest = _manifest(
        run_id,
        area,
        "locust",
        profile=config.profile_name,
        environment=config.host,
        config=config.to_manifest(),
        auth_method=auth_method,
        env_keys=list(config.extra_env) + (["BIC_AUTH_TOKEN"] if token else []),
        label=label,
        notes=notes,
    )
    step = Step(name="locust", argv=argv, env=env, timeout_seconds=locust_timeout(config))
    return registry.start(manifest, [step], sequential_supervisor)


def start_playwright_run(
    registry: RunRegistry,
    config: PlaywrightRunConfig,
    *,
    token: TokenBundle | None = None,
    settings: AppSettings,
    run_id: str | None = None,
    label: str = "",
) -> ManagedRun:
    run_id = run_id or new_run_id(TestArea.UI)
    repoint_playwright_outputs(config, run_id)
    argv = build_playwright_argv(config)
    env = build_env(token=token, playwright=config)

    notes = ["UI journey runs under the saved browser session, not the OAuth bearer token."]
    if settings.is_production_host(config.base_url):
        notes.append("Target host matched a production marker.")

    manifest = _manifest(
        run_id,
        TestArea.UI,
        "playwright",
        profile=config.test_file,
        environment=config.base_url,
        config=config.to_manifest(),
        auth_method=AuthMethod.PLAYWRIGHT_STATE,
        env_keys=["BIC_BASE_URL", "BIC_STORAGE_STATE"],
        label=label,
        notes=notes,
    )
    step = Step(name="playwright", argv=argv, env=env, timeout_seconds=playwright_timeout(config))
    return registry.start(manifest, [step], sequential_supervisor)


def start_combined_run(
    registry: RunRegistry,
    config: CombinedRunConfig,
    *,
    token: TokenBundle | None,
    auth_method: AuthMethod,
    settings: AppSettings,
    label: str = "",
) -> ManagedRun:
    """One run id covering Locust load plus a Playwright journey run under it."""
    run_id = new_run_id(TestArea.COMBINED)
    repoint_locust_outputs(config.locust, run_id)
    repoint_playwright_outputs(config.playwright, run_id)

    locust_step = Step(
        name="locust",
        argv=build_locust_argv(config.locust),
        env=build_env(token=token, extra=config.locust.extra_env),
        timeout_seconds=locust_timeout(config.locust),
        # The Locust half is interrupted on purpose when the UI journey ends, so a
        # non-zero exit from that interrupt must not fail the whole combined run.
        tolerate_failure=config.stop_locust_after_ui,
    )
    playwright_step = Step(
        name="playwright",
        argv=build_playwright_argv(config.playwright),
        env=build_env(token=token, playwright=config.playwright),
        timeout_seconds=playwright_timeout(config.playwright),
    )

    notes = [
        f"Playwright journey started {config.warmup_seconds}s after Locust, while load was active.",
        "Locust drives the BFF API; Playwright drives the real React UI in Chromium.",
    ]
    if token is not None:
        notes.append("Locust load ran under a single Databricks identity (one bearer token).")

    manifest = _manifest(
        run_id,
        TestArea.COMBINED,
        "combined",
        profile=f"{config.locust.profile_name} + {config.playwright.test_file}",
        environment=config.locust.host,
        config=config.to_manifest(),
        auth_method=auth_method,
        env_keys=list(config.locust.extra_env) + (["BIC_AUTH_TOKEN"] if token else []),
        label=label,
        notes=notes,
    )
    supervisor = make_combined_supervisor(config.warmup_seconds, config.stop_locust_after_ui)
    return registry.start(manifest, [locust_step, playwright_step], supervisor)


def busy_output_paths(registry: RunRegistry) -> set[str]:
    """Output locations currently claimed by active runs (collision preflight)."""
    busy: set[str] = set()
    for run in registry.active_runs():
        busy.update(run.manifest.artifacts.values())
    return busy


def preview_for(config: LocustRunConfig | PlaywrightRunConfig | CombinedRunConfig) -> dict:
    """Plain dict of the resolved configuration for the review step."""
    if isinstance(config, CombinedRunConfig):
        return config.to_manifest()
    return asdict(config)

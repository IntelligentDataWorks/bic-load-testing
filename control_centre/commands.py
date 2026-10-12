"""Construction of subprocess argument vectors.

Every command is built as a list of arguments and executed with ``shell=False``.
No user-supplied value is ever interpolated into a shell string, and there is no
free-form command field anywhere in the app. Secrets are passed exclusively
through the child process's ``env`` mapping, never as arguments.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from control_centre.auth import TokenBundle
from control_centre.models import LocustRunConfig, PlaywrightRunConfig
from control_centre.paths import PROJECT_ROOT, relative_to_root

# Env var names this repo's scenarios and config already use.
ENV_AUTH_TOKEN = "BIC_AUTH_TOKEN"
ENV_TEST_USER_ID = "BIC_TEST_USER_ID"
ENV_TEST_QUESTION = "BIC_TEST_QUESTION"
ENV_FULL_FLOW = "BIC_ENABLE_FULL_FLOW"
ENV_SERVING_PATH = "BIC_SERVING_ENDPOINT_PATH"
ENV_REQUEST_TIMEOUT = "BIC_REQUEST_TIMEOUT_SECONDS"
ENV_SESSION_PREFIX = "BIC_SESSION_ID_PREFIX"

# Env vars the control centre sets for Playwright (read by playwright.config.ts).
ENV_PW_BASE_URL = "BIC_BASE_URL"
ENV_PW_STORAGE_STATE = "BIC_STORAGE_STATE"
ENV_PW_TRACE = "BIC_TRACE"
ENV_PW_SCREENSHOT = "BIC_SCREENSHOT"
ENV_PW_VIDEO = "BIC_VIDEO"


def locust_executable() -> list[str]:
    """Run Locust through the current interpreter, via the stoppable launcher.

    Using ``sys.executable`` keeps the app and Locust in one virtual environment.
    ``control_centre.locust_launcher`` delegates straight to ``locust.main`` but
    also makes a Windows CTRL_BREAK stop land on Locust's graceful-shutdown path,
    so an interrupted run still writes its HTML report.
    """
    return [sys.executable, "-m", "control_centre.locust_launcher"]


def npx_executable() -> str:
    return shutil.which("npx") or "npx"


def build_locust_argv(config: LocustRunConfig) -> list[str]:
    """Explicit, fully-resolved Locust command.

    The selected ``.conf`` is read for defaults and merged with the user's
    overrides in the UI; the resulting command passes every value as a flag
    instead of ``--config``, so the source profile is never mutated and the
    preview shows exactly what will run.
    """
    argv = locust_executable()
    argv += ["-f", relative_to_root(config.locustfile)]
    argv += ["--host", config.host]
    if config.headless:
        argv.append("--headless")
    argv += ["-u", str(config.users)]
    argv += ["-r", str(config.spawn_rate)]
    argv += ["-t", config.run_time]
    argv += ["--csv", relative_to_root(config.csv_prefix)]
    argv += ["--html", relative_to_root(config.html_path)]
    # Locust otherwise keeps appending to a previous run's history file.
    argv.append("--csv-full-history")
    return argv


def build_playwright_argv(config: PlaywrightRunConfig) -> list[str]:
    """``npx playwright test`` with machine-readable reporting enabled.

    The HTML reporter stays on (it is what the existing docs demo); ``json`` is
    added alongside it so the Results and AI-diagnosis pages have structured
    data instead of scraping stdout.
    """
    argv = [npx_executable(), "playwright", "test", relative_to_root(config.test_file)]
    argv += [f"--project={config.project}"]
    if config.headed:
        argv.append("--headed")
    argv += [f"--workers={config.workers}"]
    if config.repeat_each > 1:
        argv += [f"--repeat-each={config.repeat_each}"]
    argv += [f"--timeout={config.timeout_ms}"]
    argv += [f"--output={relative_to_root(config.output_dir)}"]
    argv += ["--reporter=list,html,json"]
    if config.grep:
        argv += ["--grep", config.grep]
    return argv


def build_env(
    *,
    token: TokenBundle | None = None,
    extra: dict[str, str] | None = None,
    playwright: PlaywrightRunConfig | None = None,
) -> dict[str, str]:
    """Environment for a test subprocess.

    Starts from the server's own environment so Node/Python keep working, then
    layers the run's variables on top. The bearer token is injected here and
    nowhere else.
    """
    env = dict(os.environ)
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    # Locust's own env-var prefix: stop a stale LOCUST_* from the shell leaking in.
    env.pop("LOCUST_LOCUSTFILE", None)

    for key, value in (extra or {}).items():
        if value is None or value == "":
            env.pop(key, None)
        else:
            env[key] = str(value)

    if token is not None:
        env[ENV_AUTH_TOKEN] = token.value
    else:
        env.pop(ENV_AUTH_TOKEN, None)

    if playwright is not None:
        env[ENV_PW_BASE_URL] = playwright.base_url
        env[ENV_PW_STORAGE_STATE] = relative_to_root(playwright.storage_state)
        env[ENV_PW_TRACE] = playwright.trace
        env[ENV_PW_SCREENSHOT] = playwright.screenshot
        env[ENV_PW_VIDEO] = playwright.video
        # Keep the HTML report inside this run's directory and stop the reporter
        # from starting its own blocking web server when the run finishes.
        env["PLAYWRIGHT_HTML_OUTPUT_DIR"] = str(PROJECT_ROOT / playwright.html_report_dir)
        env["PLAYWRIGHT_HTML_OPEN"] = "never"
        env["PW_TEST_HTML_REPORT_OPEN"] = "never"
        env["PLAYWRIGHT_JSON_OUTPUT_NAME"] = str(PROJECT_ROOT / playwright.json_report_path)
        env["FORCE_COLOR"] = "0"
    return env


def build_show_report_argv(html_report_dir: Path | str) -> list[str]:
    """``npx playwright show-report <dir>`` for local report browsing."""
    return [npx_executable(), "playwright", "show-report", relative_to_root(html_report_dir)]


def build_show_trace_argv(trace_path: Path | str) -> list[str]:
    return [npx_executable(), "playwright", "show-trace", relative_to_root(trace_path)]

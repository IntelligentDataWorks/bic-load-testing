"""Preflight checks run before the Run button is enabled.

Two kinds of check:

* *toolchain* -- Python/Locust/Node/npm/Playwright/Chromium/Databricks CLI. These
  are expensive to probe, identical for every run, and are cached by the caller.
* *run-specific* -- the selected scenario or spec exists, the target URL parses,
  the required auth is held, the output directory is writable and no other run is
  already writing to the same place.

Each check carries a remedy string so a failure is actionable in the UI.
"""

from __future__ import annotations

import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

from control_centre.auth import databricks_cli
from control_centre.paths import PROJECT_ROOT, RESULTS_DIR
from control_centre.process import run_blocking

MIN_PYTHON = (3, 10)


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str = ""
    remedy: str = ""
    required: bool = True

    @property
    def blocking(self) -> bool:
        return self.required and not self.ok


def _version_check(name: str, argv: list[str], remedy: str, required: bool = True) -> Check:
    exe = argv[0]
    if shutil.which(exe) is None and not Path(exe).exists():
        return Check(name, False, f"{exe} not found on PATH", remedy, required)
    code, output = run_blocking(argv, timeout=60)
    first_line = next((ln for ln in output.splitlines() if ln.strip()), "")
    if code != 0:
        return Check(name, False, first_line or f"exit code {code}", remedy, required)
    return Check(name, True, first_line.strip(), required=required)


def check_python() -> Check:
    version = ".".join(str(p) for p in sys.version_info[:3])
    ok = sys.version_info[:2] >= MIN_PYTHON
    return Check(
        "Python",
        ok,
        f"{version} ({sys.executable})",
        remedy=f"Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+ is required.",
    )


def check_locust() -> Check:
    return _version_check(
        "Locust",
        [sys.executable, "-m", "locust", "--version"],
        remedy="Install it into this venv: uv pip install locust",
    )


def check_node() -> Check:
    return _version_check("Node.js", ["node", "--version"], remedy="Install Node.js 20+.")


def check_npm() -> Check:
    npm = shutil.which("npm") or "npm"
    return _version_check("npm", [npm, "--version"], remedy="Install Node.js (npm ships with it).")


def check_playwright() -> Check:
    npx = shutil.which("npx") or "npx"
    return _version_check(
        "Playwright",
        [npx, "playwright", "--version"],
        remedy="Install it in this folder: npm install -D @playwright/test",
    )


def _browser_cache_dirs() -> list[Path]:
    import os

    override = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    if override and override != "0":
        return [Path(override)]
    home = Path.home()
    return [
        home / "AppData" / "Local" / "ms-playwright",  # Windows
        home / "Library" / "Caches" / "ms-playwright",  # macOS
        home / ".cache" / "ms-playwright",  # Linux
    ]


def check_chromium() -> Check:
    for directory in _browser_cache_dirs():
        if not directory.exists():
            continue
        matches = sorted(directory.glob("chromium*-*"))
        if matches:
            return Check("Chromium", True, matches[-1].name)
    return Check(
        "Chromium",
        False,
        "no chromium build found in the Playwright browser cache",
        remedy="Run: npx playwright install chromium",
    )


def check_databricks_cli() -> Check:
    info = databricks_cli()
    return Check(
        "Databricks CLI",
        info.available,
        info.version or info.error,
        remedy="Install the Databricks CLI and make sure it is on PATH.",
        required=False,
    )


def toolchain_checks() -> list[Check]:
    """Every environment probe. Cache the result -- these shell out."""
    return [
        check_python(),
        check_locust(),
        check_node(),
        check_npm(),
        check_playwright(),
        check_chromium(),
        check_databricks_cli(),
    ]


def check_file_exists(label: str, relative_path: str, remedy: str = "") -> Check:
    path = PROJECT_ROOT / relative_path if relative_path else None
    if not relative_path:
        return Check(label, False, "nothing selected", remedy or "Select a file.")
    exists = path is not None and path.is_file()
    return Check(label, exists, relative_path, remedy or "Pick an existing file.")


def check_output_free(output_paths: list[str], busy_paths: set[str]) -> Check:
    """Refuse to start a run whose output collides with a run already in flight."""
    clashes = sorted({p for p in output_paths if p in busy_paths})
    if clashes:
        return Check(
            "Output collision",
            False,
            ", ".join(clashes),
            "Another active run is writing there. Wait for it or stop it first.",
        )
    return Check("Output collision", True, "no conflict with active runs")


def check_results_writable() -> Check:
    try:
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        probe = RESULTS_DIR / ".write-probe"
        probe.write_text("", encoding="utf-8")
        probe.unlink()
    except OSError as exc:
        return Check("Results directory", False, str(exc), "Check folder permissions on results/.")
    return Check("Results directory", True, str(RESULTS_DIR))


def blocking_failures(checks: list[Check]) -> list[Check]:
    return [c for c in checks if c.blocking]

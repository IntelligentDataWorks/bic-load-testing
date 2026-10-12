"""Discovery of the artefacts the repository already defines.

Nothing here invents scenario names, profile names or commands: Locust profiles
come from the ``.conf`` files on disk, scenarios from ``scenarios/*.py``, and
Playwright specs from ``tests/*.spec.ts``. Required environment variables are
read out of the scenario source (``_require_env("X")`` / ``os.getenv("X")``)
rather than hard-coded here, so a new scenario is picked up automatically.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from control_centre.models import LocustProfile, LocustScenario, PlaywrightTest, TestArea
from control_centre.paths import (
    CONFIG_DIR,
    PROJECT_ROOT,
    SCENARIOS_DIR,
    TESTS_DIR,
)

_REQUIRED_ENV_RE = re.compile(r"_require_env\(\s*[\"']([A-Z0-9_]+)[\"']\s*\)")
_OPTIONAL_ENV_RE = re.compile(r"os\.getenv\(\s*[\"']([A-Z0-9_]+)[\"']")
_TEST_TITLE_RE = re.compile(r"^\s*test\s*\(\s*['\"](.+?)['\"]", re.MULTILINE)
_LOCUST_BOOL_KEYS = {"headless", "web-ui", "only-summary", "reset-stats", "autostart", "autoquit"}

# Profiles carry no machine-readable "area" field, so classify by the scenario
# they point at -- the one piece of information that is actually in the file.
_SERVING_SCENARIOS = {"serving_endpoint_smoke.py", "serving_endpoint_load.py"}


def _leading_comment(text: str) -> str:
    """First contiguous ``#`` comment block of a config file, as a description."""
    lines: list[str] = []
    for raw in text.splitlines():
        stripped = raw.strip()
        if stripped.startswith("#"):
            lines.append(stripped.lstrip("#").strip())
        elif not stripped and lines:
            continue
        elif lines:
            break
        elif not stripped:
            continue
        else:
            break
    return " ".join(part for part in lines if part)


def parse_locust_conf(path: Path) -> dict[str, str]:
    """Parse a Locust ``.conf`` (configargparse ``key = value``) into a dict."""
    values: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return values
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith(";"):
            continue
        if "=" not in line:
            # configargparse also accepts bare flags on their own line.
            values[line.strip()] = "true"
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip()
    return values


def _profile_area(values: dict[str, str]) -> TestArea:
    locustfile = Path(values.get("locustfile", "")).name
    if locustfile in _SERVING_SCENARIOS:
        return TestArea.SERVING
    return TestArea.BFF


def _profile_display_name(path: Path) -> str:
    """``config/locust.deployed-smoke.conf`` -> ``deployed-smoke``."""
    stem = path.stem  # "locust.deployed-smoke"
    if stem.startswith("locust."):
        stem = stem[len("locust.") :]
    elif stem == "locust":
        stem = "local (root locust.conf)" if path.parent == PROJECT_ROOT else "local"
    return stem


@lru_cache(maxsize=1)
def _cached_profiles() -> tuple[LocustProfile, ...]:
    candidates: list[Path] = []
    root_conf = PROJECT_ROOT / "locust.conf"
    if root_conf.exists():
        candidates.append(root_conf)
    if CONFIG_DIR.exists():
        candidates.extend(sorted(CONFIG_DIR.glob("*.conf")))

    profiles: list[LocustProfile] = []
    seen: set[str] = set()
    for path in candidates:
        values = parse_locust_conf(path)
        if not values:
            continue
        name = _profile_display_name(path)
        if name in seen:
            name = f"{name} ({path.parent.name})"
        seen.add(name)
        profiles.append(
            LocustProfile(
                name=name,
                path=path,
                values=values,
                description=_leading_comment(path.read_text(encoding="utf-8")),
                area=_profile_area(values),
            )
        )
    return tuple(profiles)


def discover_locust_profiles(refresh: bool = False) -> list[LocustProfile]:
    """Every ``.conf`` profile in the repo (root ``locust.conf`` first)."""
    if refresh:
        _cached_profiles.cache_clear()
    return list(_cached_profiles())


def find_profile(name: str) -> LocustProfile | None:
    for profile in discover_locust_profiles():
        if profile.name == name:
            return profile
    return None


def _scenario_env(text: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    required = tuple(sorted(set(_REQUIRED_ENV_RE.findall(text))))
    optional = tuple(sorted(set(_OPTIONAL_ENV_RE.findall(text)) - set(required)))
    return required, optional


@lru_cache(maxsize=1)
def _cached_scenarios() -> tuple[LocustScenario, ...]:
    if not SCENARIOS_DIR.exists():
        return ()
    shared = ""
    auth_file = SCENARIOS_DIR / "auth.py"
    if auth_file.exists():
        shared = auth_file.read_text(encoding="utf-8")

    scenarios: list[LocustScenario] = []
    for path in sorted(SCENARIOS_DIR.glob("*.py")):
        if path.name in {"__init__.py", "auth.py"}:
            continue
        text = path.read_text(encoding="utf-8")
        # auth.py's BIC_AUTH_TOKEN applies to every scenario that inherits from it.
        required, optional = _scenario_env(text + ("\n" + shared if "TokenAuthHttpUser" in text else ""))
        docstring = ""
        match = re.search(r'^\s*"""(.*?)"""', text, re.DOTALL)
        if match:
            docstring = " ".join(match.group(1).strip().split())
        scenarios.append(
            LocustScenario(
                name=path.name,
                path=path,
                summary=docstring[:400],
                required_env=required,
                optional_env=optional,
            )
        )
    return tuple(scenarios)


def discover_locust_scenarios(refresh: bool = False) -> list[LocustScenario]:
    if refresh:
        _cached_scenarios.cache_clear()
    return list(_cached_scenarios())


def find_scenario(relative_path: str) -> LocustScenario | None:
    target = Path(relative_path).name
    for scenario in discover_locust_scenarios():
        if scenario.name == target:
            return scenario
    return None


def scenario_env_requirements(locustfile: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """(required, optional) environment variables for a locustfile path."""
    scenario = find_scenario(locustfile)
    if scenario is None:
        return (), ()
    return scenario.required_env, scenario.optional_env


@lru_cache(maxsize=1)
def _cached_playwright_tests() -> tuple[PlaywrightTest, ...]:
    if not TESTS_DIR.exists():
        return ()
    tests: list[PlaywrightTest] = []
    for path in sorted(TESTS_DIR.glob("*.spec.ts")):
        text = path.read_text(encoding="utf-8")
        titles = tuple(_TEST_TITLE_RE.findall(text))
        # A raw `npx playwright codegen` recording: single anonymous test, a
        # hard-coded absolute storageState and no assertions.
        is_draft = "test.use(" in text and "storageState" in text and titles == ("test",)
        summary = titles[0] if titles else "(no named test found)"
        tests.append(
            PlaywrightTest(
                name=path.name,
                path=path,
                titles=titles,
                summary=summary,
                is_recorded_draft=is_draft,
            )
        )
    return tuple(tests)


def discover_playwright_tests(refresh: bool = False) -> list[PlaywrightTest]:
    if refresh:
        _cached_playwright_tests.cache_clear()
    return list(_cached_playwright_tests())


def find_playwright_test(relative_path: str) -> PlaywrightTest | None:
    target = Path(relative_path).name
    for test in discover_playwright_tests():
        if test.name == target:
            return test
    return None


def refresh_all() -> None:
    """Drop every discovery cache (used by the 'rescan repository' button)."""
    _cached_profiles.cache_clear()
    _cached_scenarios.cache_clear()
    _cached_playwright_tests.cache_clear()

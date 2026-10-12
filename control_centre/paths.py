"""Canonical project paths and the containment rules every writer must obey.

Everything the app writes goes under ``results/``; ``ensure_inside`` is the single
gate that prevents a user-supplied output prefix from escaping it (``../``,
absolute paths, symlink tricks).
"""

from __future__ import annotations

from pathlib import Path

# control_centre/paths.py -> control_centre/ -> project root
PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent

CONFIG_DIR: Path = PROJECT_ROOT / "config"
SCENARIOS_DIR: Path = PROJECT_ROOT / "scenarios"
TESTS_DIR: Path = PROJECT_ROOT / "tests"
DATA_DIR: Path = PROJECT_ROOT / "data"
RESULTS_DIR: Path = PROJECT_ROOT / "results"
SCRIPTS_DIR: Path = PROJECT_ROOT / "scripts"
DOCS_DIR: Path = PROJECT_ROOT / "docs"
PLAYWRIGHT_AUTH_DIR: Path = PROJECT_ROOT / "playwright" / ".auth"
PLAYWRIGHT_STORAGE_STATE: Path = PLAYWRIGHT_AUTH_DIR / "bic-user.json"
PLAYWRIGHT_CONFIG: Path = PROJECT_ROOT / "playwright.config.ts"
APP_SETTINGS_FILE: Path = CONFIG_DIR / "app-settings.json"


class PathOutsideProjectError(ValueError):
    """Raised when a resolved path would escape its allowed base directory."""


def is_inside(candidate: Path, base: Path) -> bool:
    """True when ``candidate`` resolves to ``base`` or somewhere beneath it."""
    try:
        resolved = Path(candidate).resolve()
        resolved_base = Path(base).resolve()
    except (OSError, RuntimeError):
        return False
    return resolved == resolved_base or resolved_base in resolved.parents


def ensure_inside(candidate: Path | str, base: Path = RESULTS_DIR) -> Path:
    """Resolve ``candidate`` (relative paths are taken from the project root) and
    guarantee it stays inside ``base``.

    Raises:
        PathOutsideProjectError: when the resolved path escapes ``base``.
    """
    path = Path(candidate)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    if not is_inside(path, base):
        raise PathOutsideProjectError(
            f"{candidate!r} resolves outside the allowed directory {base}"
        )
    return path.resolve()


def relative_to_root(path: Path | str) -> str:
    """Project-relative, forward-slashed rendering of ``path`` for display/commands."""
    p = Path(path)
    try:
        if not p.is_absolute():
            p = PROJECT_ROOT / p
        return p.resolve().relative_to(PROJECT_ROOT).as_posix()
    except (ValueError, OSError):
        return Path(path).as_posix()

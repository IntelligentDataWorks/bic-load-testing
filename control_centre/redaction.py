"""Secret redaction for everything the app displays, logs or persists.

Two layers:

* pattern-based -- catches bearer headers, Databricks PATs and JWT-shaped strings
  even when the app never saw the value;
* value-based -- the live session's OAuth token/PAT are registered so any literal
  occurrence is masked, including inside a subprocess's own stdout.

Redaction is applied to log lines, command previews and the run manifest. It is
never relied on as the *only* defence: secrets are passed to child processes
through the environment, never on a command line.
"""

from __future__ import annotations

import re
from typing import Iterable

REDACTED = "***REDACTED***"

_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    # Authorization: Bearer <token>  /  "Authorization": "Bearer <token>"
    (re.compile(r"(?i)(authorization\"?\s*[:=]\s*\"?\s*(?:bearer|basic)\s+)\S+"), r"\1" + REDACTED),
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]{16,}"), "Bearer " + REDACTED),
    # Databricks personal access tokens.
    (re.compile(r"\bdapi[0-9a-fA-F]{8,}\b"), REDACTED),
    (re.compile(r"\bdkea[0-9a-zA-Z]{8,}\b"), REDACTED),
    # JWT-shaped access tokens (Databricks OAuth U2M tokens are JWTs).
    (re.compile(r"\beyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\b"), REDACTED),
    # Anything that names itself a token/secret/password in JSON or KEY=VALUE form.
    (
        re.compile(
            r"(?i)\b([A-Z0-9_]*(?:token|secret|password|passwd|api[_-]?key)[A-Z0-9_]*)"
            r"(\"?\s*[:=]\s*\"?)([^\s\"',}]{6,})"
        ),
        r"\1\2" + REDACTED,
    ),
)

# Literal secret values registered at runtime. Kept in memory only.
_registered_values: set[str] = set()


def register_secret(value: str | None) -> None:
    """Register a literal secret so it is masked wherever it appears.

    Short values are ignored: masking a 4-character string would mangle ordinary
    log text without protecting anything meaningful.
    """
    if value and len(value) >= 8:
        _registered_values.add(value)


def clear_registered_secrets() -> None:
    """Forget every registered literal (used when the user signs out)."""
    _registered_values.clear()


def redact(text: str | None) -> str:
    """Return ``text`` with every known and pattern-matched secret masked."""
    if not text:
        return "" if text is None else text
    out = text
    for value in _registered_values:
        if value in out:
            out = out.replace(value, REDACTED)
    for pattern, replacement in _PATTERNS:
        out = pattern.sub(replacement, out)
    return out


def redact_argv(argv: Iterable[str]) -> list[str]:
    """Redact each element of a command argument vector."""
    return [redact(part) for part in argv]


def redact_env(env: dict[str, str]) -> dict[str, str]:
    """Redact the values of an environment mapping (keys are kept for diagnosis)."""
    return {key: redact(value) for key, value in env.items()}


def preview_command(argv: Iterable[str]) -> str:
    """Human-readable, redacted, copy-safe single-line rendering of a command."""
    parts: list[str] = []
    for raw in redact_argv(argv):
        parts.append(f'"{raw}"' if " " in raw else raw)
    return " ".join(parts)

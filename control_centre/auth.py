"""Authentication for the control centre.

Design rules, in priority order:

1. A token is obtained in *this* process. ``scripts/get-databricks-token.ps1``
   exports ``$env:BIC_AUTH_TOKEN`` into the PowerShell session that runs it --
   a child process can never set an environment variable in its parent, so the
   Streamlit server would never see it. The app therefore calls
   ``databricks auth token`` itself, captures stdout, and keeps the value in
   Streamlit session memory.
2. The token reaches a test only through that test subprocess's own ``env``.
   It is never placed on a command line, written to a file, or logged.
3. There is no silent OAuth -> PAT fallback. The user picks a method explicitly.
"""

from __future__ import annotations

import configparser
import json
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from control_centre.paths import PLAYWRIGHT_STORAGE_STATE
from control_centre.redaction import register_secret

DATABRICKS_CFG = Path.home() / ".databrickscfg"
_TOKEN_FETCH_TIMEOUT = 120


@dataclass(frozen=True)
class TokenBundle:
    """A short-lived access token plus the non-secret facts about it.

    ``value`` never leaves session memory or a child process's environment.
    """

    value: str
    host: str
    expiry: datetime | None
    source: str  # "oauth_u2m" | "pat"
    profile: str = ""

    @property
    def expires_in_seconds(self) -> int | None:
        if self.expiry is None:
            return None
        return int((self.expiry - datetime.now(timezone.utc)).total_seconds())

    @property
    def is_expired(self) -> bool:
        remaining = self.expires_in_seconds
        return remaining is not None and remaining <= 0

    @property
    def fingerprint(self) -> str:
        """Non-reversible display handle so the UI can show 'same token' without the token."""
        import hashlib

        return hashlib.sha256(self.value.encode("utf-8")).hexdigest()[:8]


@dataclass(frozen=True)
class CliProfile:
    name: str
    host: str
    auth_type: str = ""
    valid: bool | None = None


@dataclass(frozen=True)
class ToolInfo:
    available: bool
    version: str = ""
    path: str = ""
    error: str = ""


def _run(argv: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - argv list, shell=False, no user-built strings
        argv,
        capture_output=True,
        text=True,
        timeout=timeout,
        shell=False,
        encoding="utf-8",
        errors="replace",
    )


def databricks_cli() -> ToolInfo:
    """Locate the Databricks CLI and read its version."""
    path = shutil.which("databricks")
    if not path:
        return ToolInfo(False, error="databricks CLI not found on PATH")
    try:
        proc = _run([path, "--version"], timeout=30)
    except (OSError, subprocess.SubprocessError) as exc:
        return ToolInfo(False, path=path, error=str(exc))
    if proc.returncode != 0:
        return ToolInfo(False, path=path, error=(proc.stderr or proc.stdout).strip()[:300])
    return ToolInfo(True, version=proc.stdout.strip(), path=path)


# Profile auth_types that "databricks auth token" can mint an OAuth token from.
# A "pat" profile holds a static token instead and fails with
# "databricks OAuth is not configured for this host".
OAUTH_PROFILE_TYPES = frozenset({"databricks-cli", "oauth-m2m", "oauth-u2m"})


def list_cli_profiles() -> list[CliProfile]:
    """Profiles from ``databricks auth profiles``, falling back to ``~/.databrickscfg``."""
    cli = databricks_cli()
    if cli.available:
        try:
            proc = _run([cli.path, "auth", "profiles", "--output", "json"], timeout=60)
            if proc.returncode == 0 and proc.stdout.strip():
                payload: dict[str, Any] = json.loads(proc.stdout)
                profiles = [
                    CliProfile(
                        name=item.get("name", ""),
                        host=item.get("host", ""),
                        auth_type=item.get("auth_type", ""),
                        valid=item.get("valid"),
                    )
                    for item in payload.get("profiles", [])
                    if item.get("name")
                ]
                if profiles:
                    return profiles
        except (OSError, subprocess.SubprocessError, ValueError):
            pass  # fall through to the config file

    parser = _read_databrickscfg()
    if parser is None:
        return []
    return [
        CliProfile(name=section, host=parser[section].get("host", ""))
        for section in parser.sections()
    ]


def login_command(host: str, profile: str = "") -> list[str]:
    """argv for the interactive ``databricks auth login`` browser flow."""
    cli = databricks_cli()
    exe = cli.path or "databricks"
    argv = [exe, "auth", "login", "--host", host]
    if profile:
        argv += ["--profile", profile]
    return argv


def token_command(host: str, profile: str = "") -> list[str]:
    cli = databricks_cli()
    exe = cli.path or "databricks"
    argv = [exe, "auth", "token", "--host", host]
    if profile:
        argv += ["--profile", profile]
    return argv


def _parse_expiry(raw: str | None) -> datetime | None:
    if not raw:
        return None
    text = raw.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def fetch_oauth_token(host: str, profile: str = "") -> tuple[TokenBundle | None, str]:
    """Run ``databricks auth token`` and capture the access token in-process.

    Returns ``(bundle, error_message)``. The token never touches disk; the error
    message is redacted by the caller before display.
    """
    cli = databricks_cli()
    if not cli.available:
        return None, "Databricks CLI not found on PATH. Install it and restart the app."
    try:
        proc = _run(token_command(host, profile), timeout=_TOKEN_FETCH_TIMEOUT)
    except subprocess.TimeoutExpired:
        return None, "databricks auth token timed out after 120s."
    except OSError as exc:
        return None, f"Could not start databricks CLI: {exc}"

    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).strip()
        hint = ""
        if "not logged in" in detail.lower() or "no matching" in detail.lower():
            hint = " Run the interactive sign-in first."
        return None, f"databricks auth token failed: {detail[:400]}{hint}"

    try:
        payload = json.loads(proc.stdout)
    except ValueError:
        return None, "databricks auth token did not return JSON."

    access_token = payload.get("access_token")
    if not access_token:
        return None, "databricks auth token returned no access_token."

    register_secret(access_token)
    return (
        TokenBundle(
            value=access_token,
            host=host,
            expiry=_parse_expiry(payload.get("expiry")),
            source="oauth_u2m",
            profile=profile,
        ),
        "",
    )


def make_pat_bundle(token: str, host: str, profile: str = "") -> TokenBundle:
    """Wrap a PAT. Kept in session memory only, never persisted."""
    register_secret(token)
    return TokenBundle(value=token, host=host, expiry=None, source="pat", profile=profile)


def _read_databrickscfg() -> configparser.ConfigParser | None:
    # DEFAULT is a real profile in ~/.databrickscfg, not a template: stop
    # configparser from copying its keys (including its token) into every section.
    parser = configparser.ConfigParser(default_section="__no_inherited_defaults__", interpolation=None)
    if not DATABRICKS_CFG.exists():
        return None
    try:
        parser.read(DATABRICKS_CFG, encoding="utf-8")
    except (OSError, configparser.Error):
        return None
    return parser


def list_pat_profiles() -> list[CliProfile]:
    """``~/.databrickscfg`` profiles that hold their own PAT. Names and hosts only."""
    parser = _read_databrickscfg()
    if parser is None:
        return []
    return [
        CliProfile(name=section, host=parser[section].get("host", "").strip(), auth_type="pat")
        for section in parser.sections()
        if parser[section].get("token", "").strip()
        and parser[section].get("auth_type", "pat").strip() == "pat"
    ]


def load_pat_from_profile(profile: str) -> tuple[TokenBundle | None, str]:
    """Read one profile's PAT into memory. The value never leaves the returned bundle."""
    parser = _read_databrickscfg()
    if parser is None:
        return None, f"{DATABRICKS_CFG} is missing or unreadable."
    if not parser.has_section(profile):
        return None, f"Profile {profile!r} not found in {DATABRICKS_CFG.name}."
    section = parser[profile]
    token = section.get("token", "").strip()
    host = section.get("host", "").strip().rstrip("/")
    if not token:
        return None, f"Profile {profile!r} holds no PAT."
    if not host:
        return None, f"Profile {profile!r} has no host."
    return make_pat_bundle(token, host, profile), ""


# --------------------------------------------------------------------------
# Playwright storage state
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class StorageStateInfo:
    """Non-sensitive facts about ``playwright/.auth/bic-user.json``.

    Deliberately contains no cookie names, values or origins -- only counts and
    timestamps, so the UI can report usability without exposing the session.
    """

    exists: bool
    path: Path = PLAYWRIGHT_STORAGE_STATE
    modified: datetime | None = None
    cookie_count: int = 0
    origin_count: int = 0
    earliest_expiry: datetime | None = None
    expired_cookie_count: int = 0
    parse_error: str = ""
    # The Databricks Apps proxy session is the cookie scoped to the app's own host.
    # It is the decisive signal: it lives ~24h, while short-lived SSO nonces in
    # the same file expire within minutes of capture and do not matter.
    app_host: str = ""
    app_session_found: bool = False
    app_session_expiry: datetime | None = None

    @property
    def app_session_expired(self) -> bool:
        if self.app_session_expiry is None:
            return False
        return self.app_session_expiry <= datetime.now(timezone.utc)

    @property
    def problem(self) -> str:
        """Why a Playwright run would land on a login page, or ``""`` if none is known."""
        if not self.exists:
            return "Saved Playwright session is missing."
        if self.parse_error:
            return "Saved Playwright session could not be read."
        if self.cookie_count == 0 and self.origin_count == 0:
            return "Saved Playwright session is empty."
        if self.app_host and not self.app_session_found:
            return f"Saved Playwright session has no session for {self.app_host}."
        if self.app_session_expired:
            return (
                "Saved Playwright session for the app expired at "
                f"{self.app_session_expiry:%Y-%m-%d %H:%M} UTC."
            )
        return ""

    @property
    def looks_usable(self) -> bool:
        return not self.problem

    @property
    def status_text(self) -> str:
        if not self.exists:
            return "Missing"
        if self.parse_error:
            return "Unreadable"
        if self.cookie_count == 0 and self.origin_count == 0:
            return "Empty"
        if self.app_host and not self.app_session_found:
            return "No app session"
        if self.app_session_expired:
            return "App session expired"
        return "Looks usable"


def _cookie_matches_host(cookie_domain: str, host: str) -> bool:
    domain = cookie_domain.lstrip(".").lower()
    return bool(domain) and (host == domain or host.endswith("." + domain))


def inspect_storage_state(
    path: Path = PLAYWRIGHT_STORAGE_STATE, app_url: str = ""
) -> StorageStateInfo:
    """Smoke-check the saved browser session without revealing its contents.

    With ``app_url``, also reports when the session scoped to that app's host
    expires -- the cookie the Databricks Apps proxy actually checks.
    """
    app_host = (urlparse(app_url).hostname or "").lower() if app_url else ""
    if not path.exists():
        return StorageStateInfo(exists=False, path=path)

    modified = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return StorageStateInfo(
            exists=True, path=path, modified=modified, parse_error=type(exc).__name__
        )

    cookies = payload.get("cookies") or []
    origins = payload.get("origins") or []
    now = datetime.now(timezone.utc).timestamp()

    expiries = [
        float(c["expires"])
        for c in cookies
        if isinstance(c, dict) and isinstance(c.get("expires"), (int, float)) and c["expires"] > 0
    ]
    expired = sum(1 for value in expiries if value <= now)
    earliest = (
        datetime.fromtimestamp(min(expiries), tz=timezone.utc) if expiries else None
    )

    app_cookies = [
        c
        for c in cookies
        if app_host and isinstance(c, dict) and _cookie_matches_host(str(c.get("domain", "")), app_host)
    ]
    app_expiries = [
        float(c["expires"])
        for c in app_cookies
        if isinstance(c.get("expires"), (int, float)) and c["expires"] > 0
    ]
    app_expiry = (
        datetime.fromtimestamp(max(app_expiries), tz=timezone.utc) if app_expiries else None
    )
    return StorageStateInfo(
        exists=True,
        path=path,
        modified=modified,
        cookie_count=len(cookies),
        origin_count=len(origins),
        earliest_expiry=earliest,
        expired_cookie_count=expired,
        app_host=app_host,
        app_session_found=bool(app_cookies),
        app_session_expiry=app_expiry,
    )


def codegen_command(base_url: str, storage_state: Path = PLAYWRIGHT_STORAGE_STATE) -> list[str]:
    """argv for the existing Playwright Codegen capture flow (local use only).

    Mirrors the command documented in docs/playwright-setup-and-demo.md.
    """
    npx = shutil.which("npx") or "npx"
    return [
        npx,
        "playwright",
        "codegen",
        f"--save-storage={storage_state.as_posix()}",
        base_url,
    ]

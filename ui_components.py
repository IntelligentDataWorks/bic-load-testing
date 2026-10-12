"""Small, reusable Streamlit fragments shared across pages.

Keeps each page file short and keeps one visual language for status, targets,
preflight tables and log output.
"""

from __future__ import annotations

from datetime import datetime, timezone

import streamlit as st

from control_centre.models import RunStatus, ValidationResult
from control_centre.preflight import Check
from control_centre.runs import RunManifest
from control_centre.settings import AppSettings

_STATUS_STYLE: dict[RunStatus, tuple[str, str]] = {
    RunStatus.PENDING: ("gray", ":material/schedule:"),
    RunStatus.RUNNING: ("blue", ":material/play_circle:"),
    RunStatus.PASSED: ("green", ":material/check_circle:"),
    RunStatus.FAILED: ("red", ":material/error:"),
    RunStatus.CANCELLED: ("orange", ":material/cancel:"),
    RunStatus.TIMED_OUT: ("orange", ":material/timer_off:"),
    RunStatus.ERROR: ("red", ":material/report:"),
}


def status_badge(status: RunStatus) -> None:
    color, icon = _STATUS_STYLE.get(status, ("gray", ":material/help:"))
    st.badge(status.value.replace("_", " "), icon=icon, color=color)


def target_banner(host: str, settings: AppSettings, *, label: str = "Target") -> None:
    """Always show where a run is pointed -- the single most important fact."""
    if not host:
        st.warning("No target host selected.", icon=":material/warning:")
        return
    with st.container(border=True):
        st.caption(label)
        st.markdown(f"**{host}**")
        if settings.is_production_host(host):
            st.error(
                "This host matches a production marker. Confirm the blast radius before running load.",
                icon=":material/priority_high:",
            )
        elif host.startswith("http://localhost") or host.startswith("http://127."):
            st.caption("Local target -- no Databricks auth required.")


def check_list(checks: list[Check], *, title: str = "Preflight") -> bool:
    """Render checks and return True when nothing blocking failed."""
    blocking = [c for c in checks if c.blocking]
    passed = len(checks) - len([c for c in checks if not c.ok])
    icon = ":material/check_circle:" if not blocking else ":material/error:"
    expander = st.expander(
        f"{title} -- {passed}/{len(checks)} passed", icon=icon, expanded=bool(blocking)
    )
    with expander:
        for check in checks:
            with st.container(horizontal=True, vertical_alignment="center"):
                if check.ok:
                    st.badge("ok", icon=":material/check:", color="green")
                elif check.required:
                    st.badge("fail", icon=":material/close:", color="red")
                else:
                    st.badge("optional", icon=":material/info:", color="orange")
                st.markdown(f"**{check.name}** -- {check.detail or '-'}")
            if not check.ok and check.remedy:
                st.caption(f"Fix: {check.remedy}")
    return not blocking


def validation_report(result: ValidationResult) -> bool:
    """Render validation errors/warnings; return True when the config is runnable."""
    for issue in result.errors:
        message = f"**{issue.field}** -- {issue.message}"
        if issue.remedy:
            message += f"\n\n{issue.remedy}"
        st.error(message, icon=":material/error:")
    for issue in result.warnings:
        message = f"**{issue.field}** -- {issue.message}"
        if issue.remedy:
            message += f"\n\n{issue.remedy}"
        st.warning(message, icon=":material/warning:")
    if result.ok and not result.warnings:
        st.success("Configuration validated.", icon=":material/check_circle:")
    return result.ok


def command_preview(commands: list[str], *, title: str = "Command preview (redacted)") -> None:
    st.caption(title)
    for command in commands:
        st.code(command, language="bash", wrap_lines=True)
    st.caption(
        "Commands are executed as argument arrays with shell=False. Secrets are passed "
        "through the subprocess environment, never on the command line."
    )


def log_view(lines: list[str], *, height: int = 420, key: str = "logs") -> None:
    if not lines:
        st.caption("No output yet.")
        return
    st.code("\n".join(lines), language="log", height=height, wrap_lines=False)


def format_duration(seconds: float | None) -> str:
    if seconds is None:
        return "-"
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    minutes, rest = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m {rest:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02d}m"


def format_timestamp(iso: str) -> str:
    if not iso:
        return "-"
    try:
        parsed = datetime.fromisoformat(iso)
    except ValueError:
        return iso
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone().strftime("%Y-%m-%d %H:%M:%S")


def format_ms(value: float | None) -> str:
    if value is None:
        return "-"
    if value >= 1000:
        return f"{value / 1000:.2f} s"
    return f"{value:.0f} ms"


def run_header(manifest: RunManifest) -> None:
    """Compact identity strip shown above any run's detail."""
    with st.container(horizontal=True, vertical_alignment="center"):
        status_badge(manifest.status_enum)
        st.markdown(f"**{manifest.run_id}**")
        st.badge(manifest.kind, color="violet")
        if manifest.profile:
            st.caption(manifest.profile)
    cols = st.columns(4)
    cols[0].metric("Started", format_timestamp(manifest.started_at))
    cols[1].metric("Duration", format_duration(manifest.duration_seconds))
    cols[2].metric("Exit code", "-" if manifest.exit_code is None else str(manifest.exit_code))
    cols[3].metric("Auth", manifest.auth_method)
    st.caption(f"Environment: {manifest.environment or '-'}")


def help_note(text: str) -> None:
    st.caption(text)


def section(title: str, icon: str) -> None:
    st.subheader(title, icon=icon)

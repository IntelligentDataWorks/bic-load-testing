"""Streamlit-side state: the run registry, settings, the held token and the draft
configuration shared between pages.

This is the only module that mixes Streamlit with the control-centre backend.
Everything under ``control_centre/`` stays importable and testable without
Streamlit.
"""

from __future__ import annotations

from typing import Any

import streamlit as st

from control_centre.auth import StorageStateInfo, TokenBundle, inspect_storage_state
from control_centre.models import AuthMethod, CombinedRunConfig, LocustRunConfig, PlaywrightRunConfig, TestArea
from control_centre.preflight import Check, toolchain_checks
from control_centre.process import RunRegistry
from control_centre.settings import AppSettings

# Session-state keys, in one place so pages cannot drift apart.
KEY_SETTINGS = "settings"
KEY_TOKEN = "auth_token"
KEY_AUTH_METHOD = "auth_method"
KEY_AREA = "test_area"
KEY_LOCUST_DRAFT = "locust_draft"
KEY_PLAYWRIGHT_DRAFT = "playwright_draft"
KEY_COMBINED_DRAFT = "combined_draft"
KEY_SELECTED_RUN = "selected_run_id"
KEY_ACTIVE_RUN = "active_run_id"
KEY_STRESS_ACK = "stress_acknowledged"
KEY_LAST_ERROR = "last_error"


@st.cache_resource
def get_registry() -> RunRegistry:
    """One registry per Streamlit server, surviving every script rerun."""
    return RunRegistry()


@st.cache_data(ttl="10m", show_spinner=False)
def cached_toolchain_checks(_nonce: int = 0) -> list[Check]:
    """Toolchain probes shell out, so they are cached for the whole session."""
    return toolchain_checks()


def init_state() -> None:
    """Initialise every shared key exactly once, before any page runs."""
    st.session_state.setdefault(KEY_SETTINGS, AppSettings.load())
    st.session_state.setdefault(KEY_TOKEN, None)
    st.session_state.setdefault(KEY_AUTH_METHOD, AuthMethod.NONE)
    st.session_state.setdefault(KEY_AREA, TestArea.BFF)
    st.session_state.setdefault(KEY_LOCUST_DRAFT, None)
    st.session_state.setdefault(KEY_PLAYWRIGHT_DRAFT, None)
    st.session_state.setdefault(KEY_COMBINED_DRAFT, None)
    st.session_state.setdefault(KEY_SELECTED_RUN, None)
    st.session_state.setdefault(KEY_ACTIVE_RUN, None)
    st.session_state.setdefault(KEY_STRESS_ACK, False)


# ---- accessors -------------------------------------------------------------


def settings() -> AppSettings:
    return st.session_state[KEY_SETTINGS]


def save_settings(new_settings: AppSettings) -> None:
    new_settings.save()
    st.session_state[KEY_SETTINGS] = new_settings


def token() -> TokenBundle | None:
    return st.session_state.get(KEY_TOKEN)


def set_token(bundle: TokenBundle | None, method: AuthMethod) -> None:
    st.session_state[KEY_TOKEN] = bundle
    st.session_state[KEY_AUTH_METHOD] = method


def auth_method() -> AuthMethod:
    return st.session_state.get(KEY_AUTH_METHOD, AuthMethod.NONE)


def has_usable_token() -> bool:
    bundle = token()
    return bundle is not None and not bundle.is_expired


def area() -> TestArea:
    return st.session_state.get(KEY_AREA, TestArea.BFF)


def set_area(value: TestArea) -> None:
    st.session_state[KEY_AREA] = value


def locust_draft() -> LocustRunConfig | None:
    return st.session_state.get(KEY_LOCUST_DRAFT)


def set_locust_draft(config: LocustRunConfig | None) -> None:
    st.session_state[KEY_LOCUST_DRAFT] = config
    st.session_state[KEY_STRESS_ACK] = False


def playwright_draft() -> PlaywrightRunConfig | None:
    return st.session_state.get(KEY_PLAYWRIGHT_DRAFT)


def set_playwright_draft(config: PlaywrightRunConfig | None) -> None:
    st.session_state[KEY_PLAYWRIGHT_DRAFT] = config


def combined_draft() -> CombinedRunConfig | None:
    return st.session_state.get(KEY_COMBINED_DRAFT)


def set_combined_draft(config: CombinedRunConfig | None) -> None:
    st.session_state[KEY_COMBINED_DRAFT] = config
    st.session_state[KEY_STRESS_ACK] = False


def selected_run() -> str | None:
    return st.session_state.get(KEY_SELECTED_RUN)


def set_selected_run(run_id: str | None) -> None:
    st.session_state[KEY_SELECTED_RUN] = run_id


def storage_state(app_url: str = "") -> StorageStateInfo:
    """Saved browser session, checked against ``app_url`` (default: the configured app host)."""
    return inspect_storage_state(app_url=app_url or settings().default_app_host)


def remember_active_run(run_id: str) -> None:
    st.session_state[KEY_ACTIVE_RUN] = run_id
    st.session_state[KEY_SELECTED_RUN] = run_id


def active_run_id() -> str | None:
    return st.session_state.get(KEY_ACTIVE_RUN)


def draft_for_area() -> Any:
    current = area()
    if current is TestArea.UI:
        return playwright_draft()
    if current is TestArea.COMBINED:
        return combined_draft()
    return locust_draft()

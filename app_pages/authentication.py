"""Authentication: OAuth U2M, PAT, the saved browser session, and no-auth mode."""

from __future__ import annotations

import streamlit as st

import app_state
import ui_components as ui
from control_centre.auth import (
    OAUTH_PROFILE_TYPES,
    codegen_command,
    databricks_cli,
    fetch_oauth_token,
    list_cli_profiles,
    list_pat_profiles,
    load_pat_from_profile,
    login_command,
    make_pat_bundle,
)
from control_centre.models import AuthMethod
from control_centre.paths import PLAYWRIGHT_AUTH_DIR, PLAYWRIGHT_STORAGE_STATE, relative_to_root
from control_centre.process import spawn_detached
from control_centre.redaction import clear_registered_secrets, preview_command

settings = app_state.settings()

st.title("Authentication", icon=":material/key:")
st.caption(
    "Tokens are held in this Streamlit session's memory only. They are never written to disk, "
    "never printed, and reach a test exclusively through that test subprocess's environment."
)

bundle = app_state.token()
with st.container(border=True):
    with st.container(horizontal=True, vertical_alignment="center"):
        if bundle is None:
            st.badge("Not authenticated", icon=":material/lock:", color="gray")
        elif bundle.is_expired:
            st.badge("Token expired", icon=":material/lock:", color="red")
        else:
            st.badge("Authenticated", icon=":material/verified_user:", color="green")
        st.markdown(f"Current method: **{app_state.auth_method().label}**")
    if bundle is not None:
        cols = st.columns(3)
        cols[0].metric("Source", bundle.source)
        cols[1].metric("Workspace", bundle.host.replace("https://", ""))
        remaining = bundle.expires_in_seconds
        cols[2].metric("Expires in", ui.format_duration(remaining) if remaining is not None else "unknown")
        st.caption(f"Token handle (not the token): `{bundle.fingerprint}`")
        if st.button("Sign out / forget token", icon=":material/logout:"):
            app_state.set_token(None, AuthMethod.NONE)
            clear_registered_secrets()
            st.rerun()

tabs = st.tabs(
    ["Databricks OAuth U2M", "Personal access token", "Browser session", "No auth"],
)

# --------------------------------------------------------------------------
# OAuth U2M
# --------------------------------------------------------------------------
with tabs[0]:
    st.markdown("**Preferred method** for deployed Databricks Apps, direct serving-endpoint calls and AI diagnosis.")
    st.caption(
        "Preserves your own identity end to end, which is what the app's on-behalf-of "
        "(OBO) path expects. A short-lived access token is minted by the Databricks CLI."
    )

    cli = databricks_cli()
    if not cli.available:
        st.error(
            f"Databricks CLI not available: {cli.error}",
            icon=":material/error:",
        )
    else:
        st.caption(f"CLI: {cli.version}")

    profiles = list_cli_profiles() if cli.available else []
    profile_names = [""] + [p.name for p in profiles]
    known_hosts = sorted({p.host for p in profiles if p.host} | {settings.default_workspace_host})
    auth_types = {p.name: (p.auth_type or "") for p in profiles}

    def _profile_label(name: str) -> str:
        if not name:
            return "(no profile -- use host only, recommended)"
        kind = auth_types.get(name, "")
        return f"{name}  [{kind}]" if kind else name

    chosen_profile = st.selectbox(
        "Databricks CLI profile (optional)",
        profile_names,
        format_func=_profile_label,
        key="auth_profile",
        help=(
            "Only profiles created by 'databricks auth login' (auth_type "
            "databricks-cli) can mint an OAuth token. A PAT profile cannot -- "
            "leave this empty and select the workspace host instead."
        ),
    )
    profile_host = next((p.host for p in profiles if p.name == chosen_profile), "")
    if chosen_profile and auth_types.get(chosen_profile, "") not in OAUTH_PROFILE_TYPES:
        st.warning(
            f"Profile {chosen_profile!r} is a {auth_types.get(chosen_profile) or 'unknown'} "
            "profile, not an OAuth one. 'databricks auth token' will fail with "
            "\"databricks OAuth is not configured for this host\". Clear the profile "
            "selection, or run step 1 to create an OAuth login for this host.",
            icon=":material/warning:",
        )

    host = st.selectbox(
        "Workspace host",
        known_hosts,
        index=known_hosts.index(profile_host) if profile_host in known_hosts else known_hosts.index(
            settings.default_workspace_host
        )
        if settings.default_workspace_host in known_hosts
        else 0,
        key="auth_host_choice",
    )
    custom_host = st.text_input(
        "Or type a different workspace host", value="", placeholder="https://...", key="auth_host_custom"
    ).strip()
    workspace_host = custom_host or host

    st.markdown("**Step 1 -- interactive sign-in** (once per workspace, opens a browser)")
    st.code(preview_command(login_command(workspace_host, chosen_profile)), language="bash")
    if st.button(
        "Start browser sign-in",
        icon=":material/login:",
        disabled=not cli.available or not workspace_host,
    ):
        pid = spawn_detached(login_command(workspace_host, chosen_profile))
        if pid is None:
            st.error("Could not start the Databricks CLI.", icon=":material/error:")
        else:
            st.info(
                "A browser window is opening. Complete the sign-in, then use step 2 below.",
                icon=":material/open_in_new:",
            )

    st.markdown("**Step 2 -- mint a short-lived access token**")
    st.caption(
        "The app runs `databricks auth token` itself and captures the result in memory. "
        "It does not rely on a child shell exporting an environment variable -- a child "
        "process cannot set a variable in this server's environment."
    )
    if st.button(
        "Get token",
        icon=":material/key:",
        type="primary",
        disabled=not cli.available or not workspace_host,
    ):
        with st.spinner("Requesting a token from the Databricks CLI..."):
            new_bundle, error = fetch_oauth_token(workspace_host, chosen_profile)
        if new_bundle is None:
            st.error(error, icon=":material/error:")
        else:
            app_state.set_token(new_bundle, AuthMethod.OAUTH_U2M)
            st.success("Token acquired and held in session memory.", icon=":material/check_circle:")
            st.rerun()

    if bundle is not None and bundle.source == "oauth_u2m":
        if st.button("Refresh token", icon=":material/autorenew:"):
            with st.spinner("Refreshing..."):
                new_bundle, error = fetch_oauth_token(bundle.host, bundle.profile)
            if new_bundle is None:
                st.error(error, icon=":material/error:")
            else:
                app_state.set_token(new_bundle, AuthMethod.OAUTH_U2M)
                st.rerun()

# --------------------------------------------------------------------------
# PAT
# --------------------------------------------------------------------------
with tabs[1]:
    st.warning(
        "A PAT is accepted by standard Model Serving endpoints, but it is **not** the "
        "preferred method for the Databricks Apps proxy in front of this project's deployed "
        "app, and it does not preserve the calling user's identity the way OAuth U2M does.",
        icon=":material/warning:",
    )
    st.caption(
        "There is no automatic fallback: if OAuth fails, nothing silently switches to a PAT. "
        "Choosing a PAT is always an explicit action here."
    )
    pat_profiles = list_pat_profiles()
    pat_source = st.segmented_control(
        "Source",
        ["From ~/.databrickscfg profile", "Paste manually"],
        default="From ~/.databrickscfg profile" if pat_profiles else "Paste manually",
        key="pat_source",
    )

    if pat_source == "From ~/.databrickscfg profile":
        if not pat_profiles:
            st.info("No profile in ~/.databrickscfg holds a PAT.", icon=":material/info:")
        else:
            by_name = {p.name: p for p in pat_profiles}
            chosen_pat_profile = st.selectbox(
                "Profile",
                list(by_name),
                format_func=lambda n: f"{n}  --  {by_name[n].host or 'no host'}",
                key="pat_profile",
                help="Only the profile name and host are shown. The token is read into memory when you press the button.",
            )
            chosen_host = by_name[chosen_pat_profile].host
            if chosen_host and (
                settings.is_production_host(chosen_host) or "prod" in chosen_pat_profile.lower()
            ):
                st.error(
                    f"{chosen_host} looks like a production workspace. Tests and diagnosis "
                    "calls made with this PAT will run against production.",
                    icon=":material/dangerous:",
                )
            if st.button("Use this profile's PAT", icon=":material/vpn_key:", disabled=not chosen_host):
                pat_bundle, error = load_pat_from_profile(chosen_pat_profile)
                if pat_bundle is None:
                    st.error(error, icon=":material/error:")
                else:
                    app_state.set_token(pat_bundle, AuthMethod.PAT)
                    st.success(
                        f"PAT from profile {chosen_pat_profile!r} held in session memory only.",
                        icon=":material/check_circle:",
                    )
                    st.rerun()
    else:
        pat_host = st.text_input(
            "Workspace host", value=settings.default_workspace_host, key="pat_host"
        ).strip()
        pat = st.text_input("Personal access token", value="", type="password", key="pat_value")
        if st.button("Use this PAT", icon=":material/vpn_key:", disabled=not pat or not pat_host):
            app_state.set_token(make_pat_bundle(pat, pat_host), AuthMethod.PAT)
            st.success("PAT held in session memory only.", icon=":material/check_circle:")
            st.rerun()
    st.caption(
        "The value is never persisted by this app, echoed back, or written to a manifest or log. "
        "Reading from ~/.databrickscfg does not modify that file."
    )

# --------------------------------------------------------------------------
# Playwright browser session
# --------------------------------------------------------------------------
with tabs[2]:
    storage = app_state.storage_state()
    st.markdown(f"`{relative_to_root(PLAYWRIGHT_STORAGE_STATE)}`")
    with st.container(border=True):
        cols = st.columns(3)
        cols[0].metric("State", storage.status_text)
        cols[1].metric(
            "Saved",
            ui.format_timestamp(storage.modified.isoformat()) if storage.modified else "-",
        )
        cols[2].metric("Cookies", storage.cookie_count if storage.exists else "-")
        if storage.app_session_expiry:
            verb = "expired" if storage.app_session_expired else "expires"
            st.caption(
                f"App session for `{storage.app_host}` {verb} "
                f"{ui.format_timestamp(storage.app_session_expiry.isoformat())} "
                "(the Databricks Apps proxy session lasts about 24h)."
            )
        st.caption(
            "Only counts and timestamps are shown. The file holds a live session and is never "
            "displayed, uploaded or included in an AI diagnosis payload."
        )

    if not storage.looks_usable:
        st.warning(
            f"{storage.problem} Playwright runs would be redirected to the Databricks login page "
            "until this is regenerated.",
            icon=":material/warning:",
        )

    st.markdown("**Regenerate the session** (local machine only)")
    codegen_url = st.text_input(
        "App URL", value=settings.default_app_host, key="codegen_url"
    ).strip()
    st.code(preview_command(codegen_command(codegen_url)), language="bash")
    st.caption(
        "Opens a real browser at the app. Complete the Databricks SSO sign-in by hand, wait for "
        "IRIS to load, then close both the browser and the Inspector so the state file is flushed."
    )
    if st.button("Capture browser session", icon=":material/web:", disabled=not codegen_url):
        PLAYWRIGHT_AUTH_DIR.mkdir(parents=True, exist_ok=True)
        pid = spawn_detached(codegen_command(codegen_url))
        if pid is None:
            st.error("Could not start Playwright Codegen.", icon=":material/error:")
        else:
            st.info("Codegen launched. Re-open this page after closing it to re-check the file.", icon=":material/open_in_new:")

    st.caption(f"`{relative_to_root(PLAYWRIGHT_AUTH_DIR)}/` is excluded from Git by .gitignore.")

# --------------------------------------------------------------------------
# No auth
# --------------------------------------------------------------------------
with tabs[3]:
    st.markdown("For a **local** FastAPI BFF that does not enforce auth.")
    st.caption(
        "Scenarios send no Authorization header when no token is held, which is exactly what "
        "the repository's local profiles expect. Deployed targets will return 401."
    )
    if st.button("Run without authentication", icon=":material/lock_open:"):
        app_state.set_token(None, AuthMethod.NONE)
        clear_registered_secrets()
        st.success("No-auth mode selected.", icon=":material/check_circle:")
        st.rerun()

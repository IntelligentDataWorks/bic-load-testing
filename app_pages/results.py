"""Results: Locust metrics, Playwright outcomes, combined view, reports and downloads."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

import app_state
import ui_components as ui
from control_centre.locust_results import LocustResults, parse_locust_results
from control_centre.playwright_results import PlaywrightResults, parse_playwright_results
from control_centre.reports import (
    csv_downloads,
    can_embed,
    html_download,
    launch_playwright_report,
    launch_trace_viewer,
    list_artifacts,
    open_in_browser,
    safe_path,
    zip_directory,
)
from control_centre.runs import RunManifest, list_manifests

settings = app_state.settings()

st.title("Results", icon=":material/analytics:")

manifests = list_manifests()
if not manifests:
    st.info("No runs recorded yet.", icon=":material/info:")
    if st.button("Configure a test", icon=":material/tune:", type="primary"):
        st.switch_page("app_pages/configure.py")
    st.stop()

run_ids = [m.run_id for m in manifests]
selected = app_state.selected_run()
index = run_ids.index(selected) if selected in run_ids else 0
chosen = st.selectbox("Run", run_ids, index=index, key="results_run_choice")
app_state.set_selected_run(chosen)

manifest: RunManifest = next(m for m in manifests if m.run_id == chosen)
ui.run_header(manifest)

for note in manifest.notes:
    st.caption(f"Note: {note}")

locust_prefix = manifest.artifacts.get("locust_csv_prefix")
locust_html = manifest.artifacts.get("locust_html")
pw_json = manifest.artifacts.get("playwright_json")
pw_html_dir = manifest.artifacts.get("playwright_html_dir")
pw_output_dir = manifest.artifacts.get("playwright_output_dir")

locust: LocustResults | None = (
    parse_locust_results(locust_prefix, locust_html) if locust_prefix else None
)
playwright: PlaywrightResults | None = (
    parse_playwright_results(pw_json, pw_html_dir) if pw_json else None
)


# --------------------------------------------------------------------------
# Locust
# --------------------------------------------------------------------------
def render_locust(results: LocustResults) -> None:
    if not results.found:
        st.warning(
            "No Locust output found for this run. It may have failed before any request was made.",
            icon=":material/warning:",
        )
        return

    aggregate = results.aggregated
    cols = st.columns(4)
    cols[0].metric("Total requests", results.total_requests, border=True)
    cols[1].metric(
        "Failures",
        results.total_failures,
        delta=f"{results.failure_pct:.2f}%",
        delta_color="inverse",
        border=True,
    )
    cols[2].metric(
        "Requests/s",
        f"{aggregate.requests_per_second:.2f}" if aggregate and aggregate.requests_per_second else "-",
        border=True,
    )
    cols[3].metric(
        "Peak users", results.peak_users or manifest.config.get("users", "-"), border=True
    )

    if aggregate:
        lat = st.columns(6)
        lat[0].metric("Average", ui.format_ms(aggregate.average_ms), border=True)
        lat[1].metric("Median", ui.format_ms(aggregate.median_ms), border=True)
        lat[2].metric("p90", ui.format_ms(aggregate.p("90%")), border=True)
        lat[3].metric("p95", ui.format_ms(aggregate.p("95%")), border=True)
        lat[4].metric("p99", ui.format_ms(aggregate.p("99%")), border=True)
        lat[5].metric(
            "Min / max",
            f"{ui.format_ms(aggregate.min_ms)} / {ui.format_ms(aggregate.max_ms)}",
            border=True,
        )

    if results.small_sample:
        st.warning(
            f"Only {results.total_requests} requests were recorded. Locust buckets its "
            "percentile columns, so p90/p95/p99 here are the same one or two samples rounded -- "
            "treat them as evidence the path works, not as a latency distribution.",
            icon=":material/warning:",
        )

    if results.duration_seconds:
        st.caption(
            f"Measured window {results.duration_seconds:.0f}s at up to {results.peak_users} users."
        )

    st.markdown("**Per endpoint**")
    rows = [
        {
            "Method": e.method,
            "Name": e.name,
            "Requests": e.request_count,
            "Failures": e.failure_count,
            "Failure %": round(e.failure_pct, 2),
            "Avg": ui.format_ms(e.average_ms),
            "Median": ui.format_ms(e.median_ms),
            "p95": ui.format_ms(e.p("95%")),
            "Max": ui.format_ms(e.max_ms),
            "RPS": round(e.requests_per_second or 0, 3),
        }
        for e in results.per_endpoint
    ]
    st.dataframe(rows or [{"Name": "no endpoint rows"}], hide_index=True)

    if results.history and len(results.history) > 2:
        st.markdown("**Load over time**")
        chart_rows = [
            {
                "Point": i,
                "Requests/s": h.requests_per_second or 0,
                "Failures/s": h.failures_per_second or 0,
                "Users": h.user_count,
            }
            for i, h in enumerate(results.history)
        ]
        st.line_chart(chart_rows, x="Point", y=["Requests/s", "Failures/s", "Users"])

    if results.failures:
        st.markdown("**Failures**")
        st.dataframe(
            [
                {
                    "Method": f.method,
                    "Name": f.name,
                    "Occurrences": f.occurrences,
                    "Error": f.error,
                }
                for f in results.failures
            ],
            hide_index=True,
        )
    else:
        st.success("No request-level failures recorded.", icon=":material/check_circle:")

    if results.exceptions:
        st.markdown("**Exceptions**")
        for exc in results.exceptions:
            with st.expander(f"{exc.count}x {exc.message[:120]}", icon=":material/report:"):
                st.code(exc.traceback or "(no traceback captured)", language="text")

    st.markdown("**Report**")
    html_path = safe_path(locust_html)
    with st.container(horizontal=True, wrap=True):
        if html_path and st.button("Open Locust report", icon=":material/open_in_new:", key="open_locust"):
            if not open_in_browser(html_path):
                st.error("Could not open the report.", icon=":material/error:")
        payload = html_download(html_path)
        if payload:
            st.download_button(
                "Download HTML",
                data=payload.data,
                file_name=f"{manifest.run_id}-{payload.file_name}",
                mime=payload.mime,
                icon=":material/download:",
                key="dl_locust_html",
            )
        for i, csv_payload in enumerate(csv_downloads(locust_prefix)):
            st.download_button(
                csv_payload.file_name.replace("locust_", ""),
                data=csv_payload.data,
                file_name=f"{manifest.run_id}-{csv_payload.file_name}",
                mime=csv_payload.mime,
                icon=":material/table_chart:",
                key=f"dl_csv_{i}",
            )
    if can_embed(html_path):
        preview = st.expander("Embedded report preview", icon=":material/visibility:", on_change="rerun")
        if preview.open:
            with preview:
                st.iframe(html_path, height=700)
    elif html_path:
        st.caption("Report is too large to embed reliably -- use Open or Download.")


# --------------------------------------------------------------------------
# Playwright
# --------------------------------------------------------------------------
def render_playwright(results: PlaywrightResults) -> None:
    if not results.found:
        if results.parse_error:
            st.error(f"Could not read the Playwright JSON report: {results.parse_error}", icon=":material/error:")
        else:
            st.warning(
                "No Playwright JSON report found for this run. The HTML report may still exist.",
                icon=":material/warning:",
            )
    else:
        cols = st.columns(5)
        cols[0].metric("Passed", results.passed, border=True)
        cols[1].metric("Failed", results.failed, border=True)
        cols[2].metric("Flaky", results.flaky, border=True)
        cols[3].metric("Skipped", results.skipped, border=True)
        cols[4].metric("Duration", ui.format_ms(results.duration_ms), border=True)

        st.dataframe(
            [
                {
                    "Test": t.title,
                    "File": Path(t.file).name,
                    "Project": t.project,
                    "Status": t.status,
                    "Duration": ui.format_ms(t.duration_ms),
                    "Retries": t.retries,
                }
                for t in results.tests
            ]
            or [{"Test": "no tests reported"}],
            hide_index=True,
        )

        for test in results.tests:
            if test.steps:
                with st.expander(f"Step timings -- {test.title}", icon=":material/timeline:"):
                    st.dataframe(
                        [
                            {"Step": s.title, "Duration": ui.format_ms(s.duration_ms), "Error": s.error}
                            for s in test.steps
                        ],
                        hide_index=True,
                    )

        if results.failed_tests:
            st.markdown("**Failures**")
            for test in results.failed_tests:
                with st.expander(f"{test.title}", icon=":material/error:", expanded=True):
                    for error in test.errors:
                        st.code(error, language="text", wrap_lines=True)
        if results.global_errors:
            st.markdown("**Runner errors**")
            for error in results.global_errors:
                st.code(error, language="text", wrap_lines=True)

    st.markdown("**Artefacts**")
    screenshots = list_artifacts(pw_output_dir, (".png", ".jpg", ".jpeg"))
    videos = list_artifacts(pw_output_dir, (".webm", ".mp4"))
    traces = list_artifacts(pw_output_dir, (".zip",))
    st.caption(
        f"{len(screenshots)} screenshot(s), {len(videos)} video(s), {len(traces)} trace(s) "
        "captured under this run's output directory."
    )
    for shot in screenshots[:6]:
        st.image(str(shot), caption=shot.name, width=520)
    for video in videos[:3]:
        st.video(str(video))
    for i, trace in enumerate(traces[:5]):
        if st.button(f"Open trace: {trace.name}", icon=":material/troubleshoot:", key=f"trace_{i}"):
            if launch_trace_viewer(trace) is None:
                st.error("Could not launch the trace viewer.", icon=":material/error:")

    st.markdown("**Report**")
    html_dir = safe_path(pw_html_dir)
    with st.container(horizontal=True, wrap=True):
        index_file = (html_dir / "index.html") if html_dir else None
        if index_file and index_file.exists():
            if st.button("Open HTML report", icon=":material/open_in_new:", key="open_pw"):
                if not open_in_browser(index_file):
                    st.error("Could not open the report.", icon=":material/error:")
        if html_dir and st.button(
            "Launch playwright show-report", icon=":material/web:", key="show_pw"
        ):
            if launch_playwright_report(html_dir) is None:
                st.error("Could not start npx playwright show-report.", icon=":material/error:")
            else:
                st.toast("Report server starting -- it opens in your browser.", icon=":material/web:")
        archive = zip_directory(html_dir, f"{manifest.run_id}-playwright-report.zip")
        if archive:
            st.download_button(
                "Download report (zip)",
                data=archive.data,
                file_name=archive.file_name,
                mime=archive.mime,
                icon=":material/download:",
                key="dl_pw_zip",
            )
    st.caption(
        "A Playwright HTML report is a directory of files; opening index.html directly works "
        "locally, and show-report serves it properly if the browser blocks local assets."
    )


# --------------------------------------------------------------------------
# Layout by run kind
# --------------------------------------------------------------------------
if manifest.kind == "locust":
    st.subheader("Locust results", icon=":material/monitoring:")
    render_locust(locust or parse_locust_results(locust_prefix or "", locust_html))

elif manifest.kind == "playwright":
    st.subheader("Playwright results", icon=":material/web:")
    render_playwright(playwright or parse_playwright_results(pw_json or ""))

else:  # combined
    st.subheader("Combined run", icon=":material/layers:")
    config = manifest.config or {}
    locust_config = config.get("locust", {})
    overview = st.columns(4)
    overview[0].metric("Load profile", locust_config.get("profile", "-"), border=True)
    overview[1].metric(
        "Load", f"{locust_config.get('users', '-')} users / {locust_config.get('run_time', '-')}", border=True
    )
    overview[2].metric("Warm-up", f"{config.get('warmup_seconds', '-')}s", border=True)
    overview[3].metric(
        "UI journey",
        "passed" if playwright and playwright.all_passed else "failed / unknown",
        border=True,
    )

    if locust and playwright:
        verdict_cols = st.columns(2)
        with verdict_cols[0].container(border=True, height="stretch"):
            st.markdown("**API under load**")
            st.caption(
                f"{locust.total_requests} requests, {locust.failure_pct:.2f}% failed, "
                f"avg {ui.format_ms(locust.aggregated.average_ms if locust.aggregated else None)}."
            )
        with verdict_cols[1].container(border=True, height="stretch"):
            st.markdown("**UI during that window**")
            st.caption(
                f"{playwright.passed} passed / {playwright.failed} failed, "
                f"journey took {ui.format_ms(playwright.duration_ms)}."
            )
        if playwright.failed and locust.total_failures:
            st.warning(
                "Both the API and the UI journey reported failures in the same window. "
                "They overlap in time, which is correlation, not proof of causation.",
                icon=":material/warning:",
            )
        elif playwright.failed and not locust.total_failures:
            st.warning(
                "The UI journey failed while the API reported no failures -- look at the "
                "browser trace rather than the API metrics.",
                icon=":material/warning:",
            )
        elif not playwright.failed:
            st.success(
                "The UI journey completed while load was active.", icon=":material/check_circle:"
            )

    load_tab, ui_tab = st.tabs(["Locust load", "Playwright journey"], on_change="rerun")
    if load_tab.open:
        with load_tab:
            render_locust(locust or parse_locust_results(locust_prefix or "", locust_html))
    if ui_tab.open:
        with ui_tab:
            render_playwright(playwright or parse_playwright_results(pw_json or ""))

st.subheader("Next step", icon=":material/psychology:")
if st.button("Diagnose this run with AI", icon=":material/psychology:", type="primary"):
    app_state.set_selected_run(manifest.run_id)
    st.switch_page("app_pages/diagnosis.py")

with st.expander("Run log", icon=":material/description:"):
    log_file = safe_path(manifest.artifacts.get("log"))
    if log_file and log_file.exists():
        text = log_file.read_text(encoding="utf-8", errors="replace")
        st.code(text[-40_000:], language="log", height=420)
        st.download_button(
            "Download log",
            data=text.encode("utf-8"),
            file_name=f"{manifest.run_id}-run.log",
            mime="text/plain",
            icon=":material/download:",
            key="dl_log",
        )
    else:
        st.caption("No log file recorded for this run.")

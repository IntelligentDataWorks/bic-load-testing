# Streamlit control centre

A local Streamlit application that runs and reviews every Locust scenario and
Playwright spec in this repository. Everything previously done from PowerShell --
minting a Databricks OAuth token, running a profile, opening a report -- is
available in the UI.

Related: [RUNBOOK.md](RUNBOOK.md) (setup and demo, start here),
[README.md](../README.md), [cli-reference.md](cli-reference.md),
[playwright-setup-and-demo.md](playwright-setup-and-demo.md).

---

## 1. Installation

Full prerequisites (software versions and Databricks access) are in
[RUNBOOK.md section 1](RUNBOOK.md#1-prerequisites).

```powershell
cd C:\Projects\bic-load-testing
uv venv --python 3.12
uv pip install -r requirements.txt

# Node side (already present if Playwright has been set up before)
npm install
npx playwright install chromium
```

Optional but recommended: the [Databricks CLI](https://docs.databricks.com/dev-tools/cli/)
on `PATH`, for OAuth U2M sign-in and AI diagnosis.

## 2. Starting the app

```powershell
.venv\Scripts\streamlit.exe run streamlit_app.py
```

It opens on <http://localhost:8501> and binds to `127.0.0.1` only
(see [.streamlit/config.toml](../.streamlit/config.toml)).

The app never starts a test on launch. Nothing runs until you press **Start run**.

## 3. Architecture

The Streamlit layer is thin. Every piece of real logic lives in `control_centre/`
and is importable and testable without Streamlit.

```
streamlit_app.py          entry point: page config, navigation, sidebar status
app_state.py              session state, the run registry, cached toolchain probes
ui_components.py          shared Streamlit fragments (status badges, checks, logs)
tools/render_check.py     headless render check for every page

app_pages/
  dashboard.py            environment status, recent runs, quick actions
  configure.py            area -> profile/spec -> editable fields
  authentication.py       OAuth U2M, PAT, browser session, no-auth
  run_test.py             resolved config, preflight, command preview, start
  live_logs.py            streaming output, elapsed time, stop
  results.py              Locust metrics, Playwright outcomes, reports, downloads
  diagnosis.py            LLM diagnosis of a completed run
  history.py              every recorded run and its manifest
  help.py                 what each test proves, guardrails, troubleshooting

control_centre/
  paths.py                project paths; ensure_inside() containment rule
  settings.py             guardrails, thresholds, diagnosis endpoint config
  models.py               TestArea, RunStatus, AuthMethod, *RunConfig, validation types
  discovery.py            .conf profiles, scenarios/*.py, tests/*.spec.ts
  validation.py           URL, numeric, duration, path and env validation
  preflight.py            toolchain and run-specific checks
  auth.py                 Databricks CLI OAuth, PAT, storage-state inspection
  commands.py             argv construction and subprocess environment
  locust_launcher.py      Locust entry point with a stoppable Windows handler
  process.py              background execution, log streaming, safe stop, registry
  orchestrator.py         config -> run id -> manifest -> launched run
  runs.py                 run ids, isolated result directories, manifests
  locust_results.py       CSV parsing
  playwright_results.py   JSON report parsing
  reports.py              opening, embedding, zipping and downloading reports
  diagnosis.py            LLM diagnosis adapter
  redaction.py            secret masking
```

Data flow for one run:

```
Configure page  -> LocustRunConfig / PlaywrightRunConfig / CombinedRunConfig
Run page        -> validation + preflight + redacted command preview
orchestrator    -> run id, results/<run-id>/, RunManifest, Step(argv, env)
RunRegistry     -> background thread -> subprocess (shell=False)
                   stdout/stderr -> redact() -> ring buffer + results/<run-id>/run.log
Results page    -> locust_results / playwright_results -> metrics, reports
Diagnosis page  -> sanitized summary -> Databricks serving endpoint -> manifest
```

## 4. Test areas

| Area | Tool | Included | Excluded |
|---|---|---|---|
| FastAPI BFF (local) | Locust | FastAPI BFF and its dependencies | React UI, Apps proxy, auth |
| FastAPI BFF (deployed) | Locust | Databricks Apps proxy, BFF, agent, data | React UI |
| Serving endpoint | Locust | Model Serving, agent orchestrator, downstream | React UI, BFF, Apps proxy |
| React UI | Playwright | Real browser, React app, the BFF calls it makes | Concurrency |
| Combined | Both | All of the above at once | Multiple real browsers |

Locust answers *how much load can the API take*. Playwright answers *does the
journey work*. Neither answers the other's question, which is why the combined
run exists.

## 5. Authentication

### Databricks CLI OAuth U2M (preferred)

Preferred for deployed Databricks Apps, direct serving-endpoint calls and AI
diagnosis, because it preserves the caller's own identity for the app's OBO path.

1. Pick a workspace host (and optionally a `~/.databrickscfg` profile).
2. **Start browser sign-in** runs `databricks auth login --host <host>` as a
   detached process; complete the sign-in in the browser it opens.
3. **Get token** runs `databricks auth token --host <host>` *inside the Streamlit
   process* and keeps the access token in session memory.
4. **Refresh token** re-runs step 3 when the token nears expiry.

> Why not `scripts/get-databricks-token.ps1`? That script exports
> `$env:BIC_AUTH_TOKEN` into the PowerShell session that runs it. A child process
> cannot set an environment variable in its parent, so a script launched from
> Streamlit could never give the server the token. The app therefore captures
> `databricks auth token` output itself. The PowerShell script remains valid for
> CLI-only workflows.

### PAT

Two sources, both explicit:

* **From `~/.databrickscfg` profile** -- a dropdown of profiles that hold their own
  `token` (names and hosts only are shown). Pressing **Use this profile's PAT** reads
  that one token into memory; the file is never modified. The `DEFAULT` section is
  treated as a real profile, not a template, so its token is not inherited by
  others. A profile named `*prod*`, or whose host matches a production marker,
  gets a red warning.
* **Paste manually** -- a password field.

Either way the token is held in session memory only, never persisted,
displayed or logged. A PAT is accepted by standard Model Serving endpoints but is
**not** the preferred method for the Databricks Apps proxy used by this project's
deployed app. There is no automatic OAuth-to-PAT fallback: selecting a PAT is
always explicit.

### Playwright browser session

`playwright/.auth/bic-user.json` is checked for existence, modification time and
usability (cookie count and expiry). Its contents are never shown. **Capture
browser session** launches the same `npx playwright codegen --save-storage=...`
flow documented in [playwright-setup-and-demo.md](playwright-setup-and-demo.md).
`playwright/.auth/` stays excluded from Git.

### No auth

For a local FastAPI BFF that does not enforce auth. Scenarios send no
`Authorization` header when no token is held.

## 6. How profiles are discovered

`control_centre/discovery.py` scans:

* the repository root for `locust.conf`;
* `config/` for `*.conf`.

Each file is parsed as configargparse `key = value` pairs. The leading comment
block becomes the profile description, and a profile is classified as a
serving-endpoint profile when its `locustfile` is one of the serving scenarios.

Profiles present today:

| Profile | Scenario | Host | Users | Purpose |
|---|---|---|---|---|
| `local (root locust.conf)` / `local` | `basic_scenario.py` | localhost:8000 | 1 | local, no auth |
| `local-smoke` | `smoke_healthz.py` | localhost:8000 | 1 | local health gate |
| `local-stream` | `stream_scenario.py` | localhost:8000 | 1 | local SSE timing |
| `deployed-smoke` | `smoke_healthz.py` | deployed app | 1 | gate before stress |
| `deployed-stream` | `stream_scenario.py` | deployed app | 1 | deployed SSE timing |
| `deployed-stress` | `basic_scenario.py` | deployed app | 20 | load/stress |
| `deployed-approved` | `approved_question_scenario.py` | deployed app | 1 | approved-question chat load; new session per journey plus history isolation check |
| `serving-smoke` | `serving_endpoint_smoke.py` | workspace | 1 | one direct invocation |
| `serving-stress` | `serving_endpoint_load.py` | workspace | 5 | sustained invocations |
| `prod-serving-smoke` | `serving_endpoint_smoke.py` | **PROD** workspace | 1 | PROD agent gate (approval required) |
| `prod-serving-load` | `serving_endpoint_load.py` | **PROD** workspace | 10 | PROD agent load (approval required) |

The control centre passes every value as an explicit flag rather than `--config`,
so profile keys the form does not expose (for example `stop-timeout = 330` in
`deployed-approved`) are not applied to runs started from the app.

Selecting a profile loads its values as *defaults*. Edits apply to that run only;
the `.conf` file is never modified. Use **Save these Locust values as a new
profile** to write a new file explicitly.

Required and optional environment variables are read out of the scenario source
(`_require_env("X")` and `os.getenv("X")`), so a new scenario's inputs appear in
the form automatically.

## 7. How Playwright tests are discovered

`tests/*.spec.ts` is scanned and each file's `test('...')` titles are extracted.
A file that contains a `test.use({ storageState: ... })` block and a single test
named `test` is flagged as a raw Codegen recording (that is
`tests/bic-chat-recorded.spec.ts`), so it is not mistaken for a real check.

## 8. Supported workflows

Every workflow is: **Configure test -> Use this configuration -> Run test ->
Start run**.

| Workflow | Area | Selection |
|---|---|---|
| Local BFF smoke | FastAPI BFF | profile `local-smoke` |
| Local BFF full flow | FastAPI BFF | profile `local`, `BIC_ENABLE_FULL_FLOW` on |
| Deployed app health smoke | FastAPI BFF | profile `deployed-smoke` |
| Deployed BFF load/stress | FastAPI BFF | profile `deployed-stress` + typed confirmation |
| Non-streaming chat | FastAPI BFF | profile `local` / `deployed-stress` (`basic_scenario.py`) |
| Streaming chat | FastAPI BFF | profile `local-stream` / `deployed-stream` |
| Serving-endpoint smoke | Serving endpoint | profile `serving-smoke` |
| Serving-endpoint load | Serving endpoint | profile `serving-stress` + typed confirmation |
| Authenticated UI smoke | React UI | spec `bic-smoke.spec.ts` |
| Complete chat journey | React UI | spec `bic-chat-complete.spec.ts` |
| Headed demo run | React UI | any spec, **Headed** on |
| Headless automated run | React UI | any spec, **Headed** off |
| Repeatability run | React UI | spec `bic-chat-complete.spec.ts`, `repeat-each = 3`, workers 1 |
| UI under load | Combined | Locust profile + Playwright spec + warm-up |

### Combined runs

1. Pick a Locust profile and edit it.
2. Pick a Playwright spec and edit it.
3. Set a warm-up (default 15s) and decide whether Locust stops when the journey ends.
4. One run id covers both. Locust starts, the warm-up elapses, the browser journey
   runs under load, and both reports land in the same `results/<run-id>/`.

The Results page shows the load profile, the API metrics for that window, whether
the journey passed and how long it took, and flags overlap between API failures
and UI failures as correlation rather than causation.

## 9. Execution, results and reports

* Each run gets `results/<run-id>/` with `run.log`, `manifest.json` and its
  report artefacts. Nothing is ever overwritten.
* Only one run is active at a time, so output paths cannot collide.
* **Stop** interrupts that run's process tree only, gracefully first, escalating
  to a tree kill after 20 seconds.
* Live logs auto-refresh through an `st.fragment(run_every=...)`; the rest of the
  page stays interactive.

### Locust results

Parsed from `<prefix>_stats.csv`, `_failures.csv`, `_exceptions.csv` and
`_stats_history.csv`: total requests, failures and failure percentage, average,
median, p90/p95/p99, min/max, requests per second, an endpoint breakdown, the
failure and exception tables, and a load-over-time chart. A run with fewer than
20 requests is flagged, because Locust's bucketed percentile columns then reflect
one or two samples rather than a distribution.

The HTML report can be opened, embedded (when small enough) or downloaded, and
every CSV has its own download button.

### Playwright results

Parsed from the JSON report: passed / failed / flaky / skipped, total duration,
per-test duration and retries, per-step timings, and redacted failure messages.
Screenshots, videos and traces captured under the run's output directory are
listed; a trace opens in `npx playwright show-trace`.

Reports can be opened directly, served with `npx playwright show-report`, or
downloaded as a zip (a Playwright HTML report is a directory, not one file).

### Machine-readable reporting

Runs started from the control centre use `--reporter=list,html,json` with
`PLAYWRIGHT_JSON_OUTPUT_NAME` pointing into the run directory. The existing HTML
report is preserved; JSON is added so results can be parsed instead of scraped.

## 10. AI diagnosis

**Diagnose results** on a completed run sends a compact, sanitized summary to a
configurable Databricks serving or AI Gateway endpoint and renders a structured
verdict.

Configure on the AI diagnosis page:

* workspace host;
* AI Gateway / serving-endpoint name;
* request shape -- `chat` (OpenAI-compatible `{"messages": [...]}`, used by AI
  Gateway and foundation-model endpoints) or `responses_agent` (MLflow
  `{"input": [...]}`, the contract this repo's own agent endpoint speaks);
* request timeout and max tokens;
* the thresholds sent alongside the metrics.

Authentication reuses the token already held in the session.

**What is sent:** run configuration, aggregate metrics, endpoint-level metrics,
failure and exception summaries, Playwright outcomes and timings, the configured
thresholds, and notes such as "one identity" or "sample too small". The exact
payload is viewable before sending.

**What is never sent:** tokens, authorization headers, the Playwright
storage-state file, raw response bodies and business data. The payload is passed
through the same redaction filter used for logs as a second line of defence.

The model is instructed to base findings only on the supplied metrics, to prefix
anything inferred with `Inferred:`, and to return a fixed JSON object: overall
status (Pass / Conditional Pass / Fail), executive summary, key findings, likely
bottleneck, threshold breaches, auth findings, top errors, recommended next
action and limitations. The result renders as a short executive summary with the
technical detail in an expander, downloads as Markdown or JSON, and is attached
to the run manifest.

## 11. Secret handling

* Tokens live in Streamlit session memory and nowhere else -- never in a file,
  a manifest, a log or the URL.
* A token reaches a test only through that subprocess's `env`. It is never a
  command-line argument.
* Logs, command previews and manifests pass through `control_centre/redaction.py`,
  which masks bearer headers, Databricks PATs (`dapi...`), JWT-shaped strings,
  anything named like a token/secret/password, and any literal value registered
  at runtime.
* `playwright/.auth/bic-user.json` is never displayed; only counts and timestamps.
* Every result and report path is validated to stay inside `results/`.
* Commands are argument arrays executed with `shell=False`. There is no free-form
  shell-command field anywhere in the app.

## 12. Safety controls

* Defaults are one-user smoke profiles.
* A run above the stress threshold (5 users by default) requires typing
  `RUN STRESS`.
* The target host is shown prominently on every configuration and run screen, and
  hosts matching a production marker raise an explicit reminder.
* Guardrails cap users, spawn rate, run time, Playwright workers and
  `repeat-each`, and are editable on the Help page
  (`config/app-settings.json`, no secrets).
* Nothing runs at startup.

## 13. Troubleshooting

| Symptom | Cause and fix |
|---|---|
| 401 from the deployed app or serving endpoint | Token missing or expired. Authentication -> **Get token**, then restart the run. |
| Run test says `requires BIC_AUTH_TOKEN but no token is held` | Expected: no token in this session yet. Authentication -> **Get token**. The token lives in session memory only, so it is gone after a Streamlit restart. |
| `databricks OAuth is not configured for this host` when minting | A **PAT** CLI profile was selected. Only profiles created by `databricks auth login` (auth_type `databricks-cli`) can mint an OAuth token. Clear the profile selection and pick the workspace host, or run step 1 first. The profile dropdown shows each profile's auth_type. |
| Playwright times out waiting for `New Session`; screenshot shows Databricks **Log in / Continue with SSO** | The saved browser session's Databricks Apps proxy cookie (scoped to the app host) lasts about **24 hours**. Run test now blocks with `Saved Playwright session for the app expired at ...` instead of burning the full timeout. Authentication -> **Browser session** -> **Capture browser session**, sign in, wait for IRIS to load, close the browser and Inspector. |
| AI diagnosis says `No token held` | Diagnosis reuses the session's token -- OAuth U2M **or** PAT. A PAT is not required: Authentication -> OAuth U2M -> **Get token** is enough. |
| `node` / `npx` not found in preflight | Node.js is not on this server's `PATH`. Install it and restart Streamlit (toolchain probes cache for 10 minutes). |
| Chromium missing | `npx playwright install chromium` |
| Locust reports 0 requests | A required environment variable was empty and the scenario raised at startup; the run log shows the `RuntimeError`. |
| Run shows `cancelled` immediately | Something interrupted the process tree -- check `results/<run-id>/run.log`. |
| Playwright HTML report will not embed | It is a directory. Use **Launch playwright show-report** or download the zip. |
| Stopping a run produced no HTML report | Should not happen: Locust runs through `control_centre/locust_launcher.py`, which converts the Windows stop signal into the graceful shutdown path. If it recurs, check the run log for a hard kill after the 20-second grace period. |
| "A run is already active" | Only one run at a time. Stop it from the sidebar or Live logs. |

## 14. Adding a new Locust profile

1. Create `config/locust.<name>.conf`:

   ```ini
   # One-line description -- this becomes the profile description in the UI.
   locustfile = scenarios/<scenario>.py
   headless = true
   users = 1
   spawn-rate = 1
   run-time = 10s
   host = https://...
   csv = results/<name>
   html = results/<name>.html
   ```

2. Press **Rescan repository** on the Dashboard.

Or configure a run in the UI and use **Save these Locust values as a new
profile**, which writes the same file for you.

## 15. Adding a new Locust scenario

Add `scenarios/<name>.py` subclassing `TokenAuthHttpUser` from
`scenarios/auth.py`. Use `_require_env("X")` for variables the scenario cannot
run without and `os.getenv("X", default)` for optional ones -- the Configure page
builds its environment form from exactly those calls.

## 16. Adding a new Playwright test

Add `tests/<name>.spec.ts`. Use the configured `baseURL` and the global
`storageState` instead of hard-coding either, so the control centre can retarget
the spec.

## 17. Changes made to existing tests

Two deliberate, backwards-compatible changes were required for reliable
orchestration and machine-readable reporting. With no `BIC_*` variables set,
both behave exactly as before.

1. **[playwright.config.ts](../playwright.config.ts)** -- `baseURL`,
   `storageState`, `screenshot`, `trace` and `video` now read optional
   environment variables (`BIC_BASE_URL`, `BIC_STORAGE_STATE`, `BIC_SCREENSHOT`,
   `BIC_TRACE`, `BIC_VIDEO`) and fall back to the original literals. This is what
   lets a run target a different host or capture different artefacts without
   editing the file.

2. **[scenarios/serving_endpoint_smoke.py](../scenarios/serving_endpoint_smoke.py)**
   -- the endpoint path, request timeout and session-id prefix are now read from
   `BIC_SERVING_ENDPOINT_PATH`, `BIC_REQUEST_TIMEOUT_SECONDS` and
   `BIC_SESSION_ID_PREFIX`, defaulting to the original constants. Session ids are
   still uniquely generated per invocation.

Added (nothing existing changed):

* `scenarios/serving_endpoint_load.py` -- sustained-load sibling of the serving
  smoke test, same contract, no `self.stop()`.
* `config/locust.serving-stress.conf`, `config/locust.deployed-stream.conf`,
  `config/locust.local-stream.conf`, `config/locust.local-smoke.conf` -- profiles
  for workflows the repository documented as one-off commands.

## 18. Known limitations

* **Single identity.** Every Locust virtual user shares the one bearer token held
  in the session. This is concurrency under a single Databricks principal; it
  does not exercise per-user isolation, per-user rate limits, or anything that
  varies by identity. The AI diagnosis is told this explicitly.
* **Local runner, remote target.** Latency between this machine and the workspace
  is included in every measurement. Numbers are comparable between runs from the
  same machine, not with numbers taken elsewhere.
* **Small samples have no percentiles.** A one-user, ten-second smoke run yields
  one or two measurements; Locust still prints p90/p95/p99 columns.
* **One browser journey is one user.** Playwright measures usability, not
  throughput, even during a combined run.
* **One run at a time**, by design, so results and reports cannot collide.
* **Combined-run correlation is not causation.** Overlapping API and UI failures
  are reported as overlapping in time, nothing stronger.
* **Streaming for serving endpoints is not offered**, because the repository's
  serving-endpoint scenarios are non-streaming. SSE timing lives in the
  `*-stream` BFF profiles.
* **`databricks auth login` is interactive** and runs detached; the app cannot
  detect completion, so token minting is a separate explicit step.
* **Windows-first.** Graceful stop uses `CTRL_BREAK_EVENT` plus a `SIGBREAK`
  handler; the POSIX path (`SIGINT` to the process group) is implemented but is
  less exercised.

## 19. Verifying a change to the app

```powershell
# every page renders headlessly through the real entry point
.venv\Scripts\python.exe tools\render_check.py

# byte-compile everything
.venv\Scripts\python.exe -m compileall -q control_centre app_pages tools
```

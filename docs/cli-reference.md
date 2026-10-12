# CLI Reference: Locust and Playwright from Windows PowerShell

> **New to this repository?** Start with [RUNBOOK.md](RUNBOOK.md): prerequisites,
> setup, and how to run everything from the Streamlit control centre. This document
> is the detailed reference for running the same tests **without** the app, and for
> planning a controlled stress escalation. (It was previously named
> `CLI_TESTING_DEMO_RUNBOOK.md`.)

This reference shows how to run the repository's Locust and Playwright tests directly
from Windows PowerShell, without the Streamlit control centre. It covers each test
stage, what to look for in the results, and when to increase load or stop.

Everything here was checked against the repository and against the tools installed
in this workspace:

| Tool | Version found locally | How it was checked |
|---|---|---|
| Python (repo `.venv`) | 3.12.13 | `.venv\Scripts\python.exe --version` |
| Locust | 2.46.6 | `.venv\Scripts\locust.exe --version`, `--help` |
| Node.js / npm | v24.17.0 / 11.13.0 | `node --version`, `npm --version` |
| Playwright (`@playwright/test`) | 1.63.0 | `npx playwright --version`, `test --help`, `show-report --help`, `codegen --help`, `test --list` |
| Databricks CLI | v1.4.0 | `databricks --version`, `auth token --help`, `apps logs --help`, `serving-endpoints --help` |

Every Locust config referenced below loads its user class
(`locust --config <file> -l`). None of the commands in this document were run
against the deployed App or the serving endpoint while it was being written.
**No live results are included. Every results table is blank on purpose.**

Related documents: [RUNBOOK.md](RUNBOOK.md) (setup and the Streamlit version of the demo),
[README.md](../README.md),
[playwright-setup-and-demo.md](playwright-setup-and-demo.md),
[streamlit-control-centre.md](streamlit-control-centre.md).

> **Since this was written:** `config/locust.deployed-approved.conf`
> (`scenarios/approved_question_scenario.py`) was added. It is the recommended
> session test: a new session per journey, a business verdict for every answer, and
> a session-history isolation check. See [RUNBOOK.md section 7](RUNBOOK.md#7-testing-user-sessions).
> Gap G1 below is now fixed for `basic_scenario.py`, which classifies each chat turn
> with `scenarios/chat_outcome.py`, so `action: "error"` counts as a failure.
> `stream_scenario.py` still has the gap.

---

## Contents

0. [What the repository actually tests](#0-what-the-repository-actually-tests)
1. [Preparation and authentication](#1-preparation-and-authentication)
2. [Stage 1 - Deployed FastAPI BFF with Locust](#2-stage-1---deployed-fastapi-bff-with-locust)
3. [Stage 2 - Direct serving endpoint with Locust](#3-stage-2---direct-serving-endpoint-with-locust)
4. [Stage 3 - React UI with Playwright](#4-stage-3---react-ui-with-playwright)
5. [Stage 4 - Combined: browser journey during Locust load](#5-stage-4---combined-browser-journey-during-locust-load)
6. [Stage 5 - Controlled stress escalation and recovery](#6-stage-5---controlled-stress-escalation-and-recovery)
7. [Reading the results](#7-reading-the-results)
8. [Limits and presentation notes](#8-limits-and-presentation-notes)
9. [Short technical-demo sequence](#9-short-technical-demo-sequence)
10. [Extended load and stress sequence](#10-extended-load-and-stress-sequence)
11. [Command quick reference](#11-command-quick-reference)
12. [Troubleshooting](#12-troubleshooting)
13. [Code gaps that affect this runbook](#13-code-gaps-that-affect-this-runbook)

---

## Targets

| Name | URL |
|---|---|
| Deployed Databricks App (React UI and FastAPI BFF) | `https://ds-insights-companion-ui-809065969263152.aws.databricksapps.com` |
| Databricks workspace | `https://adidas-dwhm-lh-wrk-gazelle-dev.cloud.databricks.com` |
| Serving endpoint | `https://adidas-dwhm-lh-wrk-gazelle-dev.cloud.databricks.com/serving-endpoints/ds-insights-companion-agent-dev/invocations` |

## Conventions used in every step

* **Working directory:** `C:\Projects\bic-load-testing` for every command.
* **Terminals:**
  * **Terminal A** runs Locust and holds the API token.
  * **Terminal B** runs Playwright.
  * **Terminal C** is optional and is used for monitoring.

  Environment variables such as `BIC_AUTH_TOKEN` only exist in the PowerShell window
  that set them.
* **Commands are run by hand.** Each block can be copied on its own. Nothing here
  escalates load automatically.
* **Each run gets its own output folder.** Every step starts by creating a new
  folder, `results\cli\<yyyyMMdd-HHmmss>-<label>`, and stores the path in `$Out`.
  `New-Item` is called without `-Force`, so it fails instead of reusing an existing
  folder. `results/` is gitignored. The `cli` subfolder keeps these runs separate
  from the Streamlit run folders (`results/<run-id>/`), which the control centre
  scans.
* **Why the output paths are passed explicitly.** Some config files write to fixed
  paths: `deployed-stress` writes `results/report*` and `deployed-smoke` writes
  `results/smoke*`. Running one of them twice overwrites the earlier report.
  Command-line flags override config-file values, so each command below sends the
  report to `$Out`.
* **Exit codes.** Locust exits with code `1` when any request failed. Playwright
  exits non-zero when any test failed. Check with `"exit code: $LASTEXITCODE"`.

---

## 0. What the repository actually tests

### 0.1 Locust scenarios

| Config | Scenario / user class | Target | Smoke or continuous | Health or business | What makes a request count as passed |
|---|---|---|---|---|---|
| `config/locust.deployed-smoke.conf` | `scenarios/smoke_healthz.py` / `HealthzSmokeUser` | App `/api/healthz` | Continuous: one request per second for 10 s | Health, including auth | HTTP 200 only. The `ok` field in the body is **not** checked. |
| `config/locust.deployed-stress.conf` | `scenarios/basic_scenario.py` / `BicApiUser` | App BFF | Continuous. 20 users, 2 min by default. | **Business workflow** | Status 200 plus the response shape defined in `openapi.json` (see 0.2) |
| `config/locust.deployed-stream.conf` | `scenarios/stream_scenario.py` / `BicApiStreamUser` | App `/api/chat/stream` | Continuous. 1 user, 60 s. | Business (streaming) | Status 200, the stream ends with a terminal `result` event, and there is no in-band `error` event |
| `config/locust.serving-smoke.conf` | `scenarios/serving_endpoint_smoke.py` / `ServingEndpointSmokeUser` | Serving endpoint | **Smoke only.** Sends exactly one request, then the user stops. | Business contract (the default question is `Hello`) | Status 200, a non-empty `output`, and no `error` item |
| `config/locust.serving-stress.conf` | `scenarios/serving_endpoint_load.py` / `ServingEndpointLoadUser` | Serving endpoint | Continuous. 5 users, 3 min by default. | Business contract | Same as the serving smoke test |

The local configs (`config/locust.conf`, `locust.local-*.conf`, root `locust.conf`)
target `http://localhost:8000` and are not used in this runbook.

### 0.2 The BFF business workflow in `basic_scenario.py`

`BicApiFlow` is a `SequentialTaskSet`. Each virtual user runs these tasks in order,
waits 1 to 3 s between tasks (`wait_time = between(1, 3)`), then starts again:

1. `GET /api/health`: checks `status == "ok"`, `contract_version` and `app_env`.
2. `GET /api/healthz`: checks `ok`, `who`, and `auth_mode` in {`obo`, `pat_fallback`}.
3. `GET /api/me`: checks the `MeResponse` shape.
4. `GET /api/data-sources`: checks the `DataSourcesResponse` shape.
5. `GET /api/sessions`: checks that the response is a JSON object.
6. Session ID: generated on the client with `uuid4`, **once per virtual user**.
7. `POST /api/chat` with a random question from `data/sample_questions.txt`: checks
   `session_id`, `user_query_id`, and that `action` is one of the four allowed
   values. `openapi.json` describes this call as blocking and says it takes 30 to 120 s.
8. `GET /api/session-chat?session_id=...`: checks only that the response is JSON.
9. `POST /api/visualization`: sent only when the chat result included
   `text2sql.sql_data` rows.

Steps 5 to 9 are skipped when `BIC_ENABLE_FULL_FLOW=false`. The default is `true`.

### 0.3 Authentication

| Path | Mechanism | Where it lives |
|---|---|---|
| Locust to the App BFF and to the serving endpoint | `Authorization: Bearer $env:BIC_AUTH_TOKEN`, added in `scenarios/auth.py` (`TokenAuthHttpUser.on_start`) | The current PowerShell process only. `scripts/get-databricks-token.ps1` fills it from `databricks auth token` (OAuth U2M). |
| Playwright to the React UI | Browser storage state (cookies and local storage) | `playwright/.auth/bic-user.json`, captured with `npx playwright codegen --save-storage=...`. Referenced by `playwright.config.ts` through `storageState`. |

**These two credentials are separate.** A valid API token does not make the browser
session valid, and a valid browser session does not make the API token valid. Each
one expires on its own schedule and is refreshed separately.

**OAuth compared with PAT.** Earlier runs against the deployed App rejected a PAT and
succeeded with OAuth U2M. The README says not to use a static PAT for the deployed
App. [streamlit-control-centre.md](streamlit-control-centre.md) says a PAT "is
accepted by standard Model Serving endpoints". This runbook has not verified a PAT
against this serving endpoint. **This runbook documents OAuth U2M only, for both
targets.** Do not treat PAT and OAuth as interchangeable.

### 0.4 Independent session and conversation IDs

| Scenario | How the session is created | Isolation |
|---|---|---|
| `basic_scenario.py` | Each virtual user creates one `uuid4` and keeps it, updated from the returned `session_id`, for the whole run. | One conversation per virtual user; no two users share one. **Each user adds turns to its own conversation for the whole run**, so later turns go into a longer session. |
| `stream_scenario.py` | No `session_id` is sent. The OpenAPI spec says "Omit to start a new conversation; the backend generates and returns one." | A new conversation for every request |
| `serving_endpoint_*.py` | `custom_inputs.session_id = f"{BIC_SESSION_ID_PREFIX}_{uuid4().hex}"` for every request (default prefix `load_test`) | A new session for every request. The prefix makes test sessions easy to identify. |
| `bic-chat-complete.spec.ts` | Clicks **New Session** and asserts the URL matches `session=chat_...` | A new conversation per test run, in its own browser context |

Every virtual user and every browser context uses **one real identity**: the one
token, the one `BIC_TEST_USER_ID`, and the one saved browser session. Several sessions
under one identity are not several users.

### 0.5 Streaming validation

* `stream_scenario.py` reads SSE lines until it gets `type == "result"` or
  `type == "error"`. It passes only when a terminal `result` arrives and its
  `result` contains `session_id`, `user_query_id` and `action`. It records three
  entries:
  * `POST /api/chat/stream`: Locust times this call with `stream=True`, so the
    time reflects **response headers, not the complete answer**.
  * `SSE /api/chat/stream:time_to_first_event`
  * `SSE /api/chat/stream:total_duration`: the time to the complete answer.
* `bic-chat-complete.spec.ts` reads the **whole** SSE body with
  `chatResponse.text()`, requires a terminal `result` event, requires a non-empty
  `message` or `insighter.insight`, and requires that text to be shown on the page.
* The serving-endpoint scenarios do **not** stream. They wait for one JSON response.

### 0.6 Reports

* **Locust:** `--csv <prefix>` writes `<prefix>_stats.csv`, `_failures.csv`,
  `_exceptions.csv` and `_stats_history.csv`. `--csv-full-history` records every
  entry over time. `--html <file>` writes one self-contained HTML file.
* **Playwright:** the HTML reporter writes to `playwright-report/` by default, and
  test artifacts go to `test-results/`. **Playwright empties the artifacts folder
  at the start of each run.** The commands below set
  `PLAYWRIGHT_HTML_OUTPUT_DIR`, `PLAYWRIGHT_JSON_OUTPUT_NAME` and `--output` for
  each run. The Streamlit app uses the same environment variables; they were
  confirmed in `node_modules/playwright/lib`. `PLAYWRIGHT_HTML_OPEN=never` stops the
  report server from starting and blocking the terminal after a failure.

### 0.7 Playwright tests

| Spec | Tests | Covers | Notes |
|---|---|---|---|
| `tests/bic-smoke.spec.ts` | 1 | The authenticated landing page: no login redirect, same origin, heading `WELCOME TO IRIS`, question input, **VIEW DATA SOURCES** and **NEW SESSION** buttons | Covers health and authentication only. Sends no chat. |
| `tests/bic-chat-complete.spec.ts` | 1 | The full chat journey: New Session, ask a question, stream `/api/chat/stream`, check the terminal `result`, check that the answer is shown | Business workflow. `test.setTimeout(120_000)` is set **inside the test**, so a `--timeout` command-line value does not apply to it. It does not check the exact answer wording: the expected text comes from the API payload. |
| `tests/bic-chat-recorded.spec.ts` | 1 | A raw Codegen recording | **Do not run.** It has no assertions, a hard-coded session URL and an absolute storage path. Always pass a spec file name so this test is not picked up. |

`playwright.config.ts` sets `workers: 1`, `fullyParallel: true`,
`retries: 0` (unless `CI` is set), `trace: 'retain-on-failure'`,
`screenshot: 'only-on-failure'`, `video: 'off'` and `navigationTimeout: 60_000`.
Only the `chromium` project is enabled.

---

## 1. Preparation and authentication

### 1.1 Enter the repository and activate the Python environment

**Terminal A** (and each other terminal you open):

```powershell
Set-Location C:\Projects\bic-load-testing
.\.venv\Scripts\Activate.ps1
```

* The commands in this runbook call `.venv\Scripts\locust.exe` and
  `.venv\Scripts\python.exe` directly, so they work whether or not the
  environment is activated.
* If activation fails with a script execution policy error, skip it; nothing
  below needs it. The same policy also blocks `scripts\get-databricks-token.ps1`.
  Ask your administrator what policy you may use, or allow scripts for this
  window only with `Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned`.
  This change ends when the window closes.

**Expected:** the prompt shows `(bic-load-testing)` or `(.venv)`. Nothing else is printed.

### 1.2 Check the toolchain

```powershell
.venv\Scripts\python.exe --version
.venv\Scripts\locust.exe --version
node --version
npm --version
npx playwright --version
databricks --version
Test-Path "$env:LOCALAPPDATA\ms-playwright\chromium-*"
```

**Expected:** one version line for each tool, similar to the table at the top, and
`True` for Chromium. If Chromium is missing, run `npx playwright install chromium`.
If Python packages are missing, run `uv pip install -r requirements.txt` as the
README describes.

**Go/no-go:** every command must print a version. Otherwise, stop and install the
missing tool.

### 1.3 Create the output folder for a run

Every step includes this pattern. Only the label changes:

```powershell
$Out = Join-Path $PWD "results\cli\$(Get-Date -Format yyyyMMdd-HHmmss)-<label>"
New-Item -ItemType Directory -Path $Out | Out-Null
$Out
```

`$Out` is an absolute path, so both Locust and Playwright resolve it the same
way. To find recent runs later:

```powershell
Get-ChildItem results\cli | Sort-Object Name | Select-Object -Last 10 Name
```

### 1.4 Get the OAuth U2M API token (Terminal A)

```powershell
.\scripts\get-databricks-token.ps1 -WorkspaceHost https://adidas-dwhm-lh-wrk-gazelle-dev.cloud.databricks.com
```

* The script runs `databricks auth login --host ...`, which opens a browser to sign
  in, then `databricks auth token --host ...`. It sets `$env:BIC_AUTH_TOKEN` in
  **this PowerShell process only**. The token is never written to the repository.
* **Expected:** `BIC_AUTH_TOKEN set from OAuth U2M session for https://adidas-dwhm-lh-wrk-gazelle-dev.cloud.databricks.com (length=NNN)`.
  The script prints only the length.
* Run it in the **same window** that will run Locust.

Check the expiry of the cached token. This prints only the timestamp:

```powershell
(databricks auth token --host https://adidas-dwhm-lh-wrk-gazelle-dev.cloud.databricks.com | ConvertFrom-Json).expiry
```

Read the expiry right after running the helper script. At that point the CLI cache
and `$env:BIC_AUTH_TOKEN` hold the same token. Later, `databricks auth token` may
return a newer token than the one stored in the environment variable.

If the remaining lifetime is shorter than the next run plus a safety margin, force a
refresh and load the new token again. `Out-Null` discards the output so the token is
not printed:

```powershell
databricks auth token --host https://adidas-dwhm-lh-wrk-gazelle-dev.cloud.databricks.com --force-refresh | Out-Null
.\scripts\get-databricks-token.ps1 -WorkspaceHost https://adidas-dwhm-lh-wrk-gazelle-dev.cloud.databricks.com
```

> The scenarios read the token once, when each virtual user starts. If it expires
> during a run, every later request fails with 401. That is an authentication
> failure, not a capacity result.

### 1.5 Confirm authentication is present without printing secrets

```powershell
if ($env:BIC_AUTH_TOKEN) { "BIC_AUTH_TOKEN: set (length=$($env:BIC_AUTH_TOKEN.Length))" } else { "BIC_AUTH_TOKEN: NOT set" }
if ($env:BIC_TEST_USER_ID) { "BIC_TEST_USER_ID: set" } else { "BIC_TEST_USER_ID: NOT set (needed for Stage 2 only)" }
Test-Path playwright\.auth\bic-user.json
```

Never run `$env:BIC_AUTH_TOKEN`, `Get-ChildItem Env:`, `Get-Content playwright\.auth\bic-user.json`,
or `databricks auth token` without `| ConvertFrom-Json` and a field selector. Each of
these prints a secret. Watch for this when sharing your screen.

### 1.6 Set the serving-endpoint identity (Terminal A, Stage 2 only)

`BIC_TEST_USER_ID` must be **the same identity as the token**. Do not invent a
different user. Ask the workspace who owns the token already in `$env:BIC_AUTH_TOKEN`
(step 1.4 must be done first, in this window). This calls the workspace SCIM `Me`
API, which is the same API `databricks current-user me` uses. The token is sent only
in the request header and is never printed:

```powershell
$env:BIC_TEST_USER_ID = (Invoke-RestMethod -Uri "https://adidas-dwhm-lh-wrk-gazelle-dev.cloud.databricks.com/api/2.0/preview/scim/v2/Me" -Headers @{ Authorization = "Bearer $env:BIC_AUTH_TOKEN" }).userName
"BIC_TEST_USER_ID = $env:BIC_TEST_USER_ID"
```

**Expected:** `BIC_TEST_USER_ID = <your Databricks login email>`. A 401 error means
the token is missing or expired; repeat step 1.4.

Don't use these two CLI shortcuts:

* `databricks current-user me --host ...` fails with `Error: unknown flag: --host`.
  In CLI v1.4.0 this command accepts only `--profile`.
* `databricks auth describe --host ... -o json` returns a `username`, but it
  authenticates using whatever the CLI resolves for that host. On this workstation,
  that was the `DEFAULT` profile with `auth_type: pat`, not the OAuth U2M login.
  The username may be the same person, but it doesn't prove the identity behind
  `BIC_AUTH_TOKEN`.

If the REST call is blocked, set your own Databricks login email by hand:
`$env:BIC_TEST_USER_ID = "<your Databricks login email>"`.

Optional: tag the serving-endpoint sessions so they can be identified as test data
later:

```powershell
$env:BIC_SESSION_ID_PREFIX = "cli_demo_$(Get-Date -Format yyyyMMdd)"
```

### 1.7 Check the saved browser session (Terminal B)

The repository already has an offline inspector, `control_centre.auth.inspect_storage_state`.
It reports status and expiry times only, and never prints cookie names or values:

```powershell
.venv\Scripts\python.exe -c "from control_centre.auth import inspect_storage_state as i; s=i(app_url='https://ds-insights-companion-ui-809065969263152.aws.databricksapps.com'); print(s.status_text, '| app session expiry (UTC):', s.app_session_expiry, '| captured (UTC):', s.modified)"
```

**Expected:** `Looks usable | app session expiry (UTC): <future time> | ...`.
Other possible states: `Missing`, `Unreadable`, `Empty`, `No app session`,
`App session expired`.

This check only reads cookie expiry dates in the file. It cannot see whether the
server revoked the session, whether you signed out, or whether a policy ended it
early. **The real check is the smoke test in step 3.2.** When this runbook was
written, the saved file in this workspace reported `App session expired`, so
capture a new session before any demo.

How long the session lasts depends on the Databricks Apps proxy cookie. The code
comments and the Streamlit docs describe it as about 24 hours, but this is **not
guaranteed**. Check before every demo and capture a new session when needed.

### 1.8 Capture or refresh the browser session (Terminal B)

```powershell
npx playwright codegen --save-storage=playwright/.auth/bic-user.json "https://ds-insights-companion-ui-809065969263152.aws.databricksapps.com"
```

1. Complete the Databricks SSO sign-in in the browser that opens.
2. Wait until IRIS loads and shows **WELCOME TO IRIS**.
3. Close **both** the browser window and the Playwright Inspector. The file is
   written only when both are closed.

**Expected:** the command returns without an error. Run step 1.7 again and it should
report `Looks usable`. Then run step 3.2.

The file contains live session cookies. It is gitignored (`playwright/.auth/`).
Never open, print, paste or commit it.

### 1.9 Stop a run safely

| Tool | How to stop | What happens |
|---|---|---|
| Locust in the foreground | Press **Ctrl+C once** in its window | Locust stops the users and **still writes the CSV and HTML reports**, because it catches `KeyboardInterrupt` and then saves the HTML. Requests still in flight may be cut off. Wait for the prompt to return; pressing Ctrl+C again can interrupt the report writing. |
| Locust at the end of `--run-time` | Automatic | Without `--stop-timeout`, running users are **stopped immediately** and in-flight chat calls are lost. The load stages below use `--stop-timeout 180` (`-s`), so a chat call that is under way can finish. After 180 s, Locust logs `Not all users finished their tasks & terminated in 180 seconds. Stopping them...`. |
| Playwright | Press **Ctrl+C once** | The run is interrupted and the tests are marked interrupted. The HTML report is written to `PLAYWRIGHT_HTML_OUTPUT_DIR`. |
| `npx playwright show-report` | Press **Ctrl+C** | Stops the local report server on port 9323. |

**Your requests may still be running on the server after you stop.** Stopping the
client does not cancel work the server has already accepted. The agent, Genie/SQL
and LLM calls may still finish, and the conversation may still be stored.

### 1.10 Sensitive data in results

* Locust HTML and CSV reports contain endpoint names, timings and failure messages.
  In `basic_scenario.py`, a failed shape check includes the **full response
  body** in the failure message (`...did not match ChatResult: {body}`). That body
  can contain business data, generated SQL or query results.
* Playwright traces (`trace.zip`), screenshots, videos and the HTML report can
  show rendered answers, network bodies, and request headers or cookies.
* Review these files before sharing them outside the team. Do not attach them to
  public tickets.

---

## 2. Stage 1 - Deployed FastAPI BFF with Locust

**Terminal A** runs every step in this stage and must have `BIC_AUTH_TOKEN` loaded
(step 1.4).

### Terms used in this stage

| Term | Meaning here |
|---|---|
| **Users** (`-u`) | The number of simulated clients. Each one runs the `BicApiFlow` sequence in a loop. |
| **Spawn rate** (`-r`) | How many users start per second. With `-u 20 -r 2`, all users have started after 10 s. |
| **Duration** (`-t`) | How long the load runs. It does not include the `--stop-timeout` grace period. |
| **Think time** | `between(1, 3)` s after every task, and every task is one HTTP call. |
| **Completed requests** | The `Request Count` column in Locust. A chat call that was cut off when the run stopped may not appear. |
| **Actual concurrency** | The number of requests in flight at the same moment. It is at most the number of users. `/api/chat` takes 30 to 120 s according to `openapi.json`, while the other calls and the think time take a few seconds, so **most users spend most of their time inside `/api/chat`**. Chat concurrency is therefore close to the user count. Total requests per second stays low, because each user completes roughly one loop per chat. |

This is **not isolated BFF benchmarking**. `/api/healthz` checks that the credential
works against the workspace, and `/api/chat` calls the agent serving endpoint, which
in turn calls Genie/SQL and LLM serving. Slow chat responses may come from any of
those layers.

---

### Step 1.1 - Deployed health smoke

**Purpose:** confirm the App is reachable through the Databricks Apps proxy and that
the token is accepted. Run this first, every time.

```powershell
# Terminal A - C:\Projects\bic-load-testing
$Out = Join-Path $PWD "results\cli\$(Get-Date -Format yyyyMMdd-HHmmss)-bff-health-smoke"
New-Item -ItemType Directory -Path $Out | Out-Null
.venv\Scripts\locust.exe --config config/locust.deployed-smoke.conf --csv "$Out\locust" --csv-full-history --html "$Out\locust.html"
"exit code: $LASTEXITCODE"
```

**Arguments:**
* `--config config/locust.deployed-smoke.conf`: runs `smoke_healthz.py`, 1 user,
  spawn rate 1, 10 s, headless, against the App host.
* `--csv`, `--html`: send the report to `$Out` instead of the fixed `results/smoke*` path.
* `--csv-full-history`: records the full time series in `_stats_history.csv`.

**Expected output:** `Starting Locust 2.46.6`, `Run time limit set to 10 seconds`,
and `Ramping to 1 users at a rate of 1.00 per second`. The final table shows about
10 `GET /api/healthz` requests (one per second) with `0` failures.
`exit code: 0`.

**Open the report:**

```powershell
Invoke-Item "$Out\locust.html"
```

**What to check:** the Failures tab is empty, and `/api/healthz` latency is steady.

**Go/no-go:**
* **Go** if there are 0 failures.
* **401 or 403:** stop. This is an authentication problem, not an App problem. Load
  the token again (step 1.4) in this window.
* **Other non-200 statuses or timeouts:** stop. Check the App status before going
  further.
* A pass here shows reachability and authentication only. It does not show that the
  business flow works or that the App can handle load.

---

### Step 1.2 - One-user business workflow (single pass)

**Purpose:** confirm the complete business sequence works once, including a real
`/api/chat` turn.

```powershell
# Terminal A
$Out = Join-Path $PWD "results\cli\$(Get-Date -Format yyyyMMdd-HHmmss)-bff-business-single"
New-Item -ItemType Directory -Path $Out | Out-Null
.venv\Scripts\locust.exe --config config/locust.deployed-stress.conf -u 1 -r 1 -t 90s --stop-timeout 180 --csv "$Out\locust" --csv-full-history --html "$Out\locust.html"
"exit code: $LASTEXITCODE"
```

**Arguments:**
* `--config config/locust.deployed-stress.conf`: the `basic_scenario.py`
  business flow against the App host. **The command-line `-u`, `-r` and `-t` values
  override the config's 20 users, spawn rate 5 and 2 min.**
* `-t 90s`: long enough for the user to reach and start `/api/chat`. The five
  health, profile and list calls plus think time take roughly 5 to 20 s.
* `--stop-timeout 180`: when the 90 s are up, the user finishes its current task
  before stopping, so an in-flight chat can complete. `openapi.json` says chat takes
  30 to 120 s. The whole command can take up to about 4.5 minutes.

**Expected output:** one row each for `/api/health`, `/api/healthz`, `/api/me`,
`/api/data-sources`, `/api/sessions` and `/api/chat`, plus `/api/session-chat`.
`/api/visualization` appears only when the chat returned SQL rows. There should be 0
failures.

**Open the report:** `Invoke-Item "$Out\locust.html"`

**What to check:**
* `/api/chat` shows **at least 1** request. If it shows 0, the run ended before the
  chat started; run again with a longer `-t`.
* The `/api/chat` response time is this run's single business latency sample.
* Locust does **not** show the answer text. It also counts `action: "error"` as a
  pass (see [Gap G1](#13-code-gaps-that-affect-this-runbook)). To confirm the
  answer is meaningful, use the Playwright chat journey (step 3.3) or the serving
  endpoint business question (step 2.2).

**Go/no-go:** go if there are 0 failures and at least one `/api/chat` request.
Otherwise stop, and read `$Out\locust_failures.csv`.

---

### Step 1.3 - Baseline: 1 user, 2 minutes

**Purpose:** measure latency with one user and no contention. Every later stage is
compared with this one.

```powershell
# Terminal A
$Out = Join-Path $PWD "results\cli\$(Get-Date -Format yyyyMMdd-HHmmss)-bff-business-u01-baseline"
New-Item -ItemType Directory -Path $Out | Out-Null
.venv\Scripts\locust.exe --config config/locust.deployed-stress.conf -u 1 -r 1 -t 2m --stop-timeout 180 --csv "$Out\locust" --csv-full-history --html "$Out\locust.html"
"exit code: $LASTEXITCODE"
```

**Expected output:** the same rows as step 1.2. Because chat takes 30 to 120 s, a
2-minute run yields only **about 1 to 4 `/api/chat` samples**.

**Open the report:** `Invoke-Item "$Out\locust.html"`

**What to check:** the `/api/chat` median, the maximum, and any failures. Write them
in the [comparison table](#74-comparison-table). With so few samples, the p95 and
p99 values are **not meaningful**. If the budget allows, extend this stage to
`-t 10m` to get a baseline you can use.

**Go/no-go:** go if there are 0 failures and chat latency matches what you have seen
in manual use.

---

### Step 1.4 - Small load: 5 users, 5 minutes

**Purpose:** the first run with several users in parallel.

```powershell
# Terminal A
$Out = Join-Path $PWD "results\cli\$(Get-Date -Format yyyyMMdd-HHmmss)-bff-business-u05"
New-Item -ItemType Directory -Path $Out | Out-Null
.venv\Scripts\locust.exe --config config/locust.deployed-stress.conf -u 5 -r 1 -t 5m --stop-timeout 180 --csv "$Out\locust" --csv-full-history --html "$Out\locust.html"
"exit code: $LASTEXITCODE"
```

**Arguments:** `-u 5 -r 1` starts one user per second, so all five run after about 5 s.

**Expected output:** `Ramping to 5 users at a rate of 1.00 per second`, then all
five users running. Up to five chat conversations are open at once, one per user.

**Open the report:** `Invoke-Item "$Out\locust.html"`

**What to check:**
* The failure count by endpoint, and the failure messages grouped by status code
  (see [section 7](#7-reading-the-results)).
* `/api/chat` median and p95 compared with the baseline. On the Charts tab, look at
  whether response times rise over the course of the run.
* In Terminal C, check the laptop's CPU (see step 5.2). Locust logs
  `CPU usage above 90%!` when the load generator becomes the limit.

**Go/no-go:**
* **Go** if there are 0 failures, the `/api/chat` median is within the suggested
  1.5 times the baseline, and there is no CPU warning.
* **Hold** (repeat or investigate) if latency rises but there are no errors.
* **Stop** on any 401 or 403, 429, 5xx or timeout. See the
  [stop thresholds](#63-suggested-stop-thresholds).

---

### Step 1.5 - Increased load: 10 users, 5 minutes

```powershell
# Terminal A
$Out = Join-Path $PWD "results\cli\$(Get-Date -Format yyyyMMdd-HHmmss)-bff-business-u10"
New-Item -ItemType Directory -Path $Out | Out-Null
.venv\Scripts\locust.exe --config config/locust.deployed-stress.conf -u 10 -r 1 -t 5m --stop-timeout 180 --csv "$Out\locust" --csv-full-history --html "$Out\locust.html"
"exit code: $LASTEXITCODE"
```

**Purpose, output and checks:** the same as step 1.4, with ten users. Watch for the
first 429 or 5xx, and for chat latency climbing steadily during the run.

**Open the report:** `Invoke-Item "$Out\locust.html"`

**Go/no-go:** apply the same rules as step 1.4, comparing against both the baseline
and the 5-user run. Continue to 20 users only if this stage is clean **and** the
20-user, 10-minute run fits the agreed cost budget.

---

### Step 1.6 - Sustained load: 20 users, 10 minutes

```powershell
# Terminal A
$Out = Join-Path $PWD "results\cli\$(Get-Date -Format yyyyMMdd-HHmmss)-bff-business-u20"
New-Item -ItemType Directory -Path $Out | Out-Null
.venv\Scripts\locust.exe --config config/locust.deployed-stress.conf -u 20 -r 2 -t 10m --stop-timeout 180 --csv "$Out\locust" --csv-full-history --html "$Out\locust.html"
"exit code: $LASTEXITCODE"
```

**Before you start:** check the token expiry (step 1.4). It must outlast the run by
more than 10 minutes plus the 3-minute stop grace period.

**Arguments:** `-r 2` starts all 20 users within about 10 s.

**Expected output:** 20 users running. The total run can take up to about 13 minutes.

**Open the report:** `Invoke-Item "$Out\locust.html"`

**What to check:** whether latency stays flat over 10 minutes or keeps rising (the
Charts tab and `_stats_history.csv`). Also check for errors that appear only late in
the run, and the laptop's resource use.

**Go/no-go:** a clean run is the **highest sustainable load tested so far**. It does
not prove the system has enough capacity. Go on to Stage 5 only if the team has
agreed a higher budget.

> The stage values (1, 5, 10 and 20 users; 2, 5 and 10 minutes) are starting points
> you can adjust. They do not show that capacity is sufficient.

---

### Step 1.7 - Optional: streaming path, 1 user

**Purpose:** measure the time to the first event and the time to the complete answer
on `/api/chat/stream`, which is the endpoint the UI calls.

```powershell
# Terminal A
$Out = Join-Path $PWD "results\cli\$(Get-Date -Format yyyyMMdd-HHmmss)-bff-stream-u01"
New-Item -ItemType Directory -Path $Out | Out-Null
.venv\Scripts\locust.exe --config config/locust.deployed-stream.conf --stop-timeout 180 --csv "$Out\locust" --csv-full-history --html "$Out\locust.html"
"exit code: $LASTEXITCODE"
```

**Arguments:** the config sets 1 user and 60 s. Every request uses the fixed question
`What were last week's top selling products?` and no session ID, so each request
starts a new conversation.

**Expected output:** three rows:
* `POST /api/chat/stream`, timed to the response headers.
* `SSE /api/chat/stream:time_to_first_event`.
* `SSE /api/chat/stream:total_duration`, the time to the complete answer.

A failure in the stream is counted in **both** the POST row and the
`total_duration` row.

**Open the report:** `Invoke-Item "$Out\locust.html"`

**Go/no-go:** go if there are 0 failures. Use `total_duration`, not the POST row, as
the complete-answer latency. Keep streaming runs separate from `basic_scenario` runs.

---

## 3. Stage 2 - Direct serving endpoint with Locust

**Terminal A**, with `BIC_AUTH_TOKEN` (step 1.4) and `BIC_TEST_USER_ID` (step 1.6) set.

**What this bypasses:** the React UI, the Databricks Apps proxy and its
authentication, and the FastAPI BFF, including the BFF's
normalize, persist and `user_query_id` finalize step described in `openapi.json`.

**What still runs:** Model Serving, the `ds-insights-companion-agent-dev` agent
orchestrator, and everything below it (Genie/SQL and LLM serving), as the
`serving_endpoint_load.py` docstring describes. A failure here is in the agent or a
layer below it.

**Request contract**, reused exactly from the scenarios (MLflow ResponsesAgent):

```json
{"input": [{"role": "user", "content": "<BIC_TEST_QUESTION or Hello>"}],
 "custom_inputs": {"session_id": "<prefix>_<uuid hex>", "user_id": "<BIC_TEST_USER_ID>"}}
```

A request passes only with HTTP 200, a non-empty `output`, no top-level `error`, and no
`output` item with `type == "error"`. A 200 response alone is not enough.

**Timeouts:** `BIC_REQUEST_TIMEOUT_SECONDS` defaults to 180 s. A request that hits the
limit is recorded as a failure. Use `--stop-timeout 190` so an in-flight call can
finish or reach its own timeout.

---

### Step 2.1 - One successful invocation

**Purpose:** confirm the payload contract and authentication with the cheapest call.

```powershell
# Terminal A
Remove-Item Env:BIC_TEST_QUESTION -ErrorAction SilentlyContinue   # use the scenario default "Hello"
$Out = Join-Path $PWD "results\cli\$(Get-Date -Format yyyyMMdd-HHmmss)-serving-smoke-hello"
New-Item -ItemType Directory -Path $Out | Out-Null
.venv\Scripts\locust.exe --config config/locust.serving-smoke.conf --csv "$Out\locust" --csv-full-history --html "$Out\locust.html"
"exit code: $LASTEXITCODE"
```

**Arguments:** the config runs `serving_endpoint_smoke.py`, 1 user, `run-time = 200s`,
with the workspace as host.

**Expected output:** exactly **1** POST to
`/serving-endpoints/ds-insights-companion-agent-dev/invocations` with 0 failures.
The user calls `self.stop()` after this request. **Locust 2.46.6 does not exit when
every user has stopped**, so the process sits idle until 200 s have passed. After the
request appears in the stats table, you can press **Ctrl+C once** to finish early;
the report is still written.

**Open the report:** `Invoke-Item "$Out\locust.html"`

**Go/no-go:**
* **Go** if there is 1 request and 0 failures.
* `RuntimeError: BIC_TEST_USER_ID must be set...` means step 1.6 was skipped.
* A 401 failure comes with the hint
  `BIC_AUTH_TOKEN is likely missing/expired in this shell`.
* A 403 means the identity lacks permission on the endpoint. That is not a capacity
  problem.

---

### Step 2.2 - One realistic business question

**Purpose:** send a single business question that goes through the agent and the data
layer. The question is the one `tests/bic-chat-complete.spec.ts` already uses.

```powershell
# Terminal A
$env:BIC_TEST_QUESTION = 'How many articles do we have in Training KCC for SS27?'
$Out = Join-Path $PWD "results\cli\$(Get-Date -Format yyyyMMdd-HHmmss)-serving-smoke-business"
New-Item -ItemType Directory -Path $Out | Out-Null
.venv\Scripts\locust.exe --config config/locust.serving-smoke.conf --csv "$Out\locust" --csv-full-history --html "$Out\locust.html"
"exit code: $LASTEXITCODE"
```

**Expected output:** 1 request with 0 failures. The latency is usually much higher than
for `Hello`. Treat it as a single sample.

**Open the report:** `Invoke-Item "$Out\locust.html"`

**What to check:** the response time. The scenario does not log the answer text. It
checks only that `output` is non-empty and has no error item. Content correctness
is checked in step 3.3.

**Go/no-go:** go if there is 1 request and 0 failures. Leave `BIC_TEST_QUESTION` set
for the load steps, so they use the realistic question.

> **Why not raise the smoke run time?** `serving_endpoint_smoke.py` calls
> `self.stop()` after one request. A longer `-t` or a higher `-u` only adds idle time,
> plus one request per extra user. Continuous load needs
> `config/locust.serving-stress.conf` (`serving_endpoint_load.py`).

---

### Step 2.3 - Continuous 1-user baseline

```powershell
# Terminal A (BIC_TEST_QUESTION still set from step 2.2)
$Out = Join-Path $PWD "results\cli\$(Get-Date -Format yyyyMMdd-HHmmss)-serving-load-u01-baseline"
New-Item -ItemType Directory -Path $Out | Out-Null
.venv\Scripts\locust.exe --config config/locust.serving-stress.conf -u 1 -r 1 -t 5m --stop-timeout 190 --csv "$Out\locust" --csv-full-history --html "$Out\locust.html"
"exit code: $LASTEXITCODE"
```

**Arguments:** `serving_endpoint_load.py` sends one invocation after another, with 1
to 3 s of think time between them and a new session ID for each. `-t 5m` replaces the
config's 3 minutes, because each business invocation can take tens of seconds and a
shorter run gives too few samples.

**Expected output:** one row for the endpoint, with a request count that depends on
the latency, and 0 failures.

**Open the report:** `Invoke-Item "$Out\locust.html"`

**Go/no-go:** go if there are 0 failures. Record the median and maximum as the direct
serving baseline.

---

### Step 2.4 - Serving load progression

Each serving invocation is a full agent run, including LLM calls and SQL. The steps
are smaller than in the BFF stages to limit cost. Run each stage separately and
review it before starting the next.

| Stage | Users | Spawn rate | Duration | `$Out` label |
|---|---:|---:|---:|---|
| Small | 3 | 1 | 5m | `serving-load-u03` |
| Config default | 5 | 1 | 5m | `serving-load-u05` |
| Increased | 10 | 1 | 5m | `serving-load-u10` |
| Sustained (only if budget agreed) | 20 | 2 | 10m | `serving-load-u20` |

The command for the 3-user stage is below. For each later stage, change `-u`, `-r`,
`-t` and the label to the values in the table:

```powershell
# Terminal A
$Out = Join-Path $PWD "results\cli\$(Get-Date -Format yyyyMMdd-HHmmss)-serving-load-u03"
New-Item -ItemType Directory -Path $Out | Out-Null
.venv\Scripts\locust.exe --config config/locust.serving-stress.conf -u 3 -r 1 -t 5m --stop-timeout 190 --csv "$Out\locust" --csv-full-history --html "$Out\locust.html"
"exit code: $LASTEXITCODE"
```

**Open the report:** `Invoke-Item "$Out\locust.html"`

**What to check:** 429 responses (endpoint rate limits or throttling), 5xx responses,
timeouts after 180 s, `agent response contained an error`, and latency compared with
the step 2.3 baseline.

**Go/no-go:** use the same rules as the BFF stages and the
[stop thresholds](#63-suggested-stop-thresholds). A stage passes with 0 failures and
a median within the suggested 1.5 times the baseline.

---

## 4. Stage 3 - React UI with Playwright

**Terminal B.** It does not need `BIC_AUTH_TOKEN`; it uses
`playwright/.auth/bic-user.json`.

Playwright checks that browser workflows work and that the answer appears on the
page. It is **not** the main tool for high-volume load. Each journey drives a real
Chromium browser for 30 to 120 s or more.

| Don't confuse | With |
|---|---|
| `--repeat-each=N` (N runs of the test) | N users at the same time. With `--workers=1`, repeats run **one after another**. |
| `--workers=N` (the maximum number of parallel worker processes) | Actual concurrency. That is the lower of `workers` and the number of runnable tests. One spec with one test and no `--repeat-each` gives **one** journey, whatever `--workers` is set to. |
| A separate browser context for each test | A separate authenticated identity. Every context loads the **same** storage state, so it is the same user. |
| Test duration in the report | Backend latency. Test duration also includes navigation, rendering, and Playwright's own waits. |

Never run `npx playwright test` without a spec file. It would also run
`bic-chat-recorded.spec.ts`.

---

### Step 3.1 - Refresh browser authentication when needed

Run step 1.7. If the result is anything other than `Looks usable`, or if step 3.2
lands on a login page, run step 1.8.

### Step 3.2 - Authenticated landing-page smoke

**Purpose:** confirm the saved session works and the App shell renders.

```powershell
# Terminal B - C:\Projects\bic-load-testing
$Out = Join-Path $PWD "results\cli\$(Get-Date -Format yyyyMMdd-HHmmss)-ui-smoke"
New-Item -ItemType Directory -Path $Out | Out-Null
$env:PLAYWRIGHT_HTML_OUTPUT_DIR = "$Out\html-report"
$env:PLAYWRIGHT_JSON_OUTPUT_NAME = "$Out\results.json"
$env:PLAYWRIGHT_HTML_OPEN = "never"
npx playwright test tests/bic-smoke.spec.ts --project=chromium --workers=1 --output "$Out\artifacts" --reporter "list,html,json"
"exit code: $LASTEXITCODE"
```

**Arguments:**
* `--project=chromium`: the only enabled project.
* `--output`: the folder for traces and screenshots from this run. Playwright empties
  it at the start of the run, which is why each run gets its own folder.
* `--reporter "list,html,json"`: `list` prints to the console, while `html` and `json`
  write to the folders set in the environment variables above. The value is quoted
  so PowerShell does not split it at the commas.

**Expected output:** `1 passed`, `exit code: 0`.

**Open the report:**

```powershell
npx playwright show-report "$Out\html-report"
```

Press Ctrl+C in this terminal to stop the report server.

**Go/no-go:**
* **Go** if it shows `1 passed`.
* A failure on `not.toHaveURL(login|signin|...)`, or a timeout waiting for
  `WELCOME TO IRIS`, almost always means the browser session has expired. Run step 1.8.

---

### Step 3.3 - Complete chat journey, visible in Chromium (demo)

**Purpose:** show the whole product path: browser, React, Apps proxy, BFF,
`/api/chat/stream`, the agent, and the rendered answer.

```powershell
# Terminal B
$Out = Join-Path $PWD "results\cli\$(Get-Date -Format yyyyMMdd-HHmmss)-ui-chat-headed"
New-Item -ItemType Directory -Path $Out | Out-Null
$env:PLAYWRIGHT_HTML_OUTPUT_DIR = "$Out\html-report"
$env:PLAYWRIGHT_JSON_OUTPUT_NAME = "$Out\results.json"
$env:PLAYWRIGHT_HTML_OPEN = "never"
npx playwright test tests/bic-chat-complete.spec.ts --project=chromium --headed --workers=1 --output "$Out\artifacts" --reporter "list,html,json"
"exit code: $LASTEXITCODE"
```

**Arguments:** `--headed` opens a visible browser window. The test sets its own
120 s limit, so `--timeout` has no effect.

**Expected output:** Chromium opens IRIS already signed in. The test clicks **New
Session**, types `How many articles do we have in Training KCC for SS27?` and sends
it. The answer appears on the page, and the console shows `1 passed`.

**Open the report:** `npx playwright show-report "$Out\html-report"`

**What to check:** the test duration and the step timings, including the
`waitForResponse` step for `/api/chat/stream`. If the test fails, see step 3.6.

**Go/no-go:** go if it shows `1 passed`. A timeout at 120 s under light load means the
chat is slower than the test allows. It does not by itself mean the UI is broken.
See [Gap G4](#13-code-gaps-that-affect-this-runbook).

---

### Step 3.4 - Repeat the complete journey sequentially

**Purpose:** check stability over several runs, one after another.

```powershell
# Terminal B
$Out = Join-Path $PWD "results\cli\$(Get-Date -Format yyyyMMdd-HHmmss)-ui-chat-repeat3"
New-Item -ItemType Directory -Path $Out | Out-Null
$env:PLAYWRIGHT_HTML_OUTPUT_DIR = "$Out\html-report"
$env:PLAYWRIGHT_JSON_OUTPUT_NAME = "$Out\results.json"
$env:PLAYWRIGHT_HTML_OPEN = "never"
npx playwright test tests/bic-chat-complete.spec.ts --project=chromium --repeat-each=3 --workers=1 --output "$Out\artifacts" --reporter "list,html,json"
"exit code: $LASTEXITCODE"
```

**Arguments:** `--repeat-each=3 --workers=1` runs three journeys **one after another**.
Each one creates its own new session.

**Expected output:** `3 passed`.

**Open the report:** `npx playwright show-report "$Out\html-report"`

**Go/no-go:** go if it shows `3 passed`. If one run is flaky (fails and then passes),
investigate before demonstrating under load.

---

### Step 3.5 - Small concurrent browser test (optional)

**Is isolation good enough?** Partly.
* Each test gets a **separate browser context** and clicks **New Session**, so the
  runs do not share a conversation.
* `fullyParallel: true` lets repeated runs be spread across workers.
* Limit: all contexts share **one identity**.
* Limit: `getByText(QUESTION_TEXT).first()` could be satisfied by another visible
  element with the same text, such as a session title, if the UI shows one. The
  check on the answer text is specific to the session.
* The Streamlit guardrail caps workers at 4. The command line has no such limit.

```powershell
# Terminal B
$Out = Join-Path $PWD "results\cli\$(Get-Date -Format yyyyMMdd-HHmmss)-ui-chat-w2x2"
New-Item -ItemType Directory -Path $Out | Out-Null
$env:PLAYWRIGHT_HTML_OUTPUT_DIR = "$Out\html-report"
$env:PLAYWRIGHT_JSON_OUTPUT_NAME = "$Out\results.json"
$env:PLAYWRIGHT_HTML_OPEN = "never"
npx playwright test tests/bic-chat-complete.spec.ts --project=chromium --repeat-each=2 --workers=2 --output "$Out\artifacts" --reporter "list,html,json"
"exit code: $LASTEXITCODE"
```

**Expected output:** the list reporter says it is running 2 tests with 2 workers, then shows `2 passed`. The two
journeys start close together but are not synchronized.

**Open the report:** `npx playwright show-report "$Out\html-report"`

**What to check:** whether the two runs overlapped in time. The start times are in
`$Out\results.json`, under `suites[].specs[].tests[].results[].startTime`. Two
journeys in parallel are still just two browsers, not a load test.

**Go/no-go:** go if it shows `2 passed`. Do not scale browsers further to generate
load; use Locust for that.

---

### Step 3.6 - Open the report and inspect failure traces and screenshots

```powershell
# Terminal B - $Out still holds the run you want to inspect
npx playwright show-report "$Out\html-report"
Get-ChildItem "$Out\artifacts" -Recurse -Include trace.zip, *.png | Select-Object FullName
npx playwright show-trace "<full path to trace.zip from the list above>"
```

* With the default config, traces are kept only for failed tests
  (`retain-on-failure`) and screenshots are taken only on failure.
* In the trace, check the network tab: the status and timing of
  `/api/chat/stream`, and the final screenshot, which may show a login page, an
  error bubble or an empty answer.
* **Traces contain request and response bodies and page content**, which can include
  business data. See section 1.10.

---

## 5. Stage 4 - Combined: browser journey during Locust load

**Purpose:** show that the UI still works while there is backend traffic. This is a
functional check under load, not a capacity measurement.

**Before you start:** step 1.4 (5 users, 5 minutes) and step 3.3 must both have passed
on their own.

### Terminal A - modest Locust business load

```powershell
# Terminal A - C:\Projects\bic-load-testing, token loaded
$Out = Join-Path $PWD "results\cli\$(Get-Date -Format yyyyMMdd-HHmmss)-combined-locust-u05"
New-Item -ItemType Directory -Path $Out | Out-Null
Get-Date -Format o | Set-Content "$Out\started-at.txt"
.venv\Scripts\locust.exe --config config/locust.deployed-stress.conf -u 5 -r 1 -t 5m --stop-timeout 180 --csv "$Out\locust" --csv-full-history --html "$Out\locust.html"
Get-Date -Format o | Set-Content "$Out\ended-at.txt"
"exit code: $LASTEXITCODE"
```

### Terminal B - one complete chat journey during that load

Start this about **60 s after** Terminal A shows all 5 users running, so the backend
is busy with chat calls:

```powershell
# Terminal B - C:\Projects\bic-load-testing
$Out = Join-Path $PWD "results\cli\$(Get-Date -Format yyyyMMdd-HHmmss)-combined-ui-chat"
New-Item -ItemType Directory -Path $Out | Out-Null
$env:PLAYWRIGHT_HTML_OUTPUT_DIR = "$Out\html-report"
$env:PLAYWRIGHT_JSON_OUTPUT_NAME = "$Out\results.json"
$env:PLAYWRIGHT_HTML_OPEN = "never"
Get-Date -Format o | Set-Content "$Out\started-at.txt"
npx playwright test tests/bic-chat-complete.spec.ts --project=chromium --headed --workers=1 --output "$Out\artifacts" --reporter "list,html,json"
Get-Date -Format o | Set-Content "$Out\ended-at.txt"
"exit code: $LASTEXITCODE"
```

**What this shows:** while five simulated users send business traffic through the BFF,
a real user can still create a session, get a streamed answer and see it rendered.

**Extra workload:** the browser adds its own requests, including the page load, any API
calls the UI makes, and one `/api/chat/stream`. These **do not appear in the Locust
report**. The backend saw five Locust users plus one browser user.

**Reports:** there are two separate folders, `...-combined-locust-u05` and
`...-combined-ui-chat`, each with `started-at.txt` and `ended-at.txt` timestamps
(ISO 8601, local time zone). To relate them, compare these timestamps with the Unix
`Timestamp` column in `_stats_history.csv`.

```powershell
Invoke-Item "<path to ...-combined-locust-u05>\locust.html"
npx playwright show-report "<path to ...-combined-ui-chat>\html-report"
```

**Go/no-go:**
* **Pass:** Playwright shows `1 passed` and Locust shows no errors during the
  overlap.
* **UI timeout with no Locust errors:** the journey took longer than 120 s under load.
  Record this as degraded responsiveness, not as a functional break.
* **Failures in both at the same time:** they overlapped in time. That is not proof
  that one caused the other.

---

## 6. Stage 5 - Controlled stress escalation and recovery

**Goal:** find the **highest load you have tested that the system sustains**, and the
**first stage where performance degrades**, without causing an uncontrolled outage.

### 6.1 Agree these before the session starts

| Item | Agreed value |
|---|---|
| Environment (dev only, **never production**) | |
| Maximum users | |
| Maximum duration per stage | |
| Total session time and cost budget (LLM, SQL, serving) | |
| Who else must be told (App owner, serving endpoint owner) | |
| Named person who can stop the test | |

The Streamlit control centre enforces guardrails (`config/app-settings.json`: at most
50 users, a spawn rate of 20, 1800 s run time, and typed confirmation above 5 users).
**The command line enforces none of these.** The operator is the only guardrail.

### 6.2 Before and during each stage

1. **Review the previous stage** against the comparison table. Do not escalate after a
   degraded or unexplained result.
2. **Check the token expiry** (step 1.4). It must outlast the stage plus the 3-minute
   grace period.
3. **Monitor the load generator.** In Terminal C, the counter names below assume an
   English version of Windows:

   ```powershell
   Get-Counter -Counter '\Processor(_Total)\% Processor Time','\Memory\Available MBytes','\Network Interface(*)\Bytes Total/sec' -SampleInterval 5 -Continuous
   ```

   Press Ctrl+C to stop. Any of these means the results reflect the laptop, not the
   server:
   * sustained CPU above about 80 %
   * very low available memory
   * Locust's `CPU usage above 90%!` warning
   * VPN saturation or instability
4. **Monitor the server side**, where your identity has permission to do so:
   * Databricks App logs. Find the App name with `databricks apps list`, then run
     `databricks apps logs <app-name> --follow --host https://adidas-dwhm-lh-wrk-gazelle-dev.cloud.databricks.com`.
     The App name is not recorded in this repository, and the logs may contain
     business data. Alternatively, open the App's **Logs** and compute pages in the
     workspace UI.
   * Serving endpoint state and metrics: open the endpoint's metrics page in the
     workspace UI, or run
     `databricks serving-endpoints get ds-insights-companion-agent-dev --host https://adidas-dwhm-lh-wrk-gazelle-dev.cloud.databricks.com`
     for the state and configuration, and
     `databricks serving-endpoints export-metrics ds-insights-companion-agent-dev --host https://adidas-dwhm-lh-wrk-gazelle-dev.cloud.databricks.com`
     for Prometheus-format metrics.
   * Downstream: Genie/SQL warehouse query history and any LLM endpoint throttling
     visible to your team.
5. **Separate authentication failures from capacity failures.** 401 and 403 responses
   are about identity or token expiry. Stop, re-authenticate, and restart the stage. Do
   not count them as capacity results.

### 6.3 Suggested stop thresholds

> **These are suggested starting thresholds, not agreed pass criteria.** Replace them
> with values your team signs off. The control centre's own defaults in
> `config/app-settings.json` (`max_failure_pct: 1.0`, `max_p95_ms: 5000`) were set
> for aggregate request metrics. They are **not** calibrated for a chat call that
> takes 30 to 120 s.

| Signal | Suggested "degraded, do not escalate" | Suggested "stop now (Ctrl+C)" |
|---|---|---|
| Failure rate (all requests) | Above 1 % for the stage | Above 5 %, or rising steadily for 2 minutes or more |
| 429 (throttling) | Any | Continuing for more than about 1 minute |
| 5xx | Any | Several a minute, or continuing |
| Timeouts or `stop-timeout` kills | Any | Continuing |
| `/api/chat` or serving median | More than 1.5 times the baseline | More than 3 times the baseline, or still climbing when the stage ends |
| p95 (only with at least 20 samples) | More than 2 times the baseline p95 | Not a stop signal on its own |
| 401 or 403 | Not a capacity signal | Stop, fix authentication, and restart |
| Load generator CPU warning | The result is invalid for this stage | Reduce load or distribute it |

**Stop immediately and escalate** if you see any **data-isolation failure**, for
example one session's answer, history or data appearing in another session. Do the
same for any unexpected side effect: errors reported by other teams, other apps
affected, alerts, or unexpected data written.

### 6.4 Manual escalation stage (template, one stage at a time)

Set the three values by hand for **each** stage, within the agreed budget. Suggested
steps above 20 users are about +50 % each time (for example 30, 45, then 60 if
agreed), with at least 10 minutes per stage.

```powershell
# Terminal A - edit these three values by hand for each stage
$Users = 30
$SpawnRate = 2
$RunTime = "10m"
$Out = Join-Path $PWD "results\cli\$(Get-Date -Format yyyyMMdd-HHmmss)-bff-stress-u$Users"
New-Item -ItemType Directory -Path $Out | Out-Null
.venv\Scripts\locust.exe --config config/locust.deployed-stress.conf -u $Users -r $SpawnRate -t $RunTime --stop-timeout 180 --csv "$Out\locust" --csv-full-history --html "$Out\locust.html"
"exit code: $LASTEXITCODE"
```

For the serving endpoint, use the same template with
`--config config/locust.serving-stress.conf`, `--stop-timeout 190` and the label
`serving-stress-u$Users`.

**Open the report:** `Invoke-Item "$Out\locust.html"`

**Go/no-go after each stage:** only escalate if the stage was clean against section
6.3. Record the stage as **last stable** or **first degraded**. Do not use unlimited
retries, and do not escalate automatically.

**Cancelling a stage:** press Ctrl+C once in Terminal A, and wait for the report to be
written. Remember that requests already sent may still be running on the server (see
step 1.9).

### 6.5 Recovery check after saturation

Wait until the server-side metrics return to idle, or at least 5 minutes. Then repeat
the one-user baseline:

```powershell
# Terminal A
$Out = Join-Path $PWD "results\cli\$(Get-Date -Format yyyyMMdd-HHmmss)-bff-business-u01-recovery"
New-Item -ItemType Directory -Path $Out | Out-Null
.venv\Scripts\locust.exe --config config/locust.deployed-stress.conf -u 1 -r 1 -t 2m --stop-timeout 180 --csv "$Out\locust" --csv-full-history --html "$Out\locust.html"
"exit code: $LASTEXITCODE"
```

Then run step 3.3 (one UI journey) once.

**Recovered (suggested):** 0 failures, and chat latency comparable to the step 1.3
baseline. If not, report it to the App and endpoint owners before running anything
else.

### 6.6 Record the outcome

| Item | Value |
|---|---|
| Last stable stage (users, duration, report path) | |
| First degraded stage (users, duration, report path) | |
| First symptom (latency, 429, 5xx, timeouts) | |
| Load generator healthy during those stages? | |
| Recovery result | |

**A failed stage does not identify the bottleneck.** It could be in the Apps proxy,
the BFF, the agent, Genie/SQL, LLM serving, rate limits on one identity, the network,
or the laptop. Relate the failure to server logs and metrics before naming a cause.

---

## 7. Reading the results

### 7.1 Locust

| Measure | Where to find it | How to read it |
|---|---|---|
| Request count and failures | HTML **Statistics** table; `_stats.csv` (`Request Count`, `Failure Count`) | Failure rate = failures divided by requests, for each endpoint and for the `Aggregated` row |
| Failure detail | HTML **Failures** tab; `_failures.csv` (`Method, Name, Error, Occurrences`) | Group by error text: `unexpected status 401`, `429`, `5xx`, JSON or shape errors, `agent response contained an error`, timeouts |
| Median, p95, p99 | `_stats.csv` columns `50%`, `95%`, `99%` | Locust rounds these values into buckets. **With fewer than about 20 samples** (the control centre's `SMALL_SAMPLE_THRESHOLD`), p95 and p99 are close to the maximum and mean little. Report the individual values instead. |
| Throughput | `Requests/s` | Chat is slow, so the aggregate requests per second is mostly health and list calls. Report `/api/chat` requests per second separately, or better, completed chats per minute. |
| Time series | HTML **Charts**; `_stats_history.csv` | Look for steady rises, which usually indicate queueing, and for periods of errors |
| Timeouts | Failure messages | The serving scenarios time out at 180 s. The BFF scenarios have **no client-side timeout** (see Gap G2). |
| 401 or 403 | Failure messages | Authentication or permission. Not capacity. |
| 429 | Failure messages | Throttling or rate limiting. This is a capacity signal, but the limit may be per identity (only one identity is used here). |
| 5xx | Failure messages | A server-side error. Check the App and endpoint logs. |

**Streaming timing:** on `/api/chat/stream`, the POST row is the time to the response
headers, `:time_to_first_event` is the time to the first SSE line, and
`:total_duration` is the time to the complete answer. `basic_scenario.py`'s `/api/chat`
blocks until the answer is complete, so its time is the complete-answer time. The
serving scenarios are not streamed; their time is the complete response time.
Playwright's test duration includes the complete stream plus rendering.

**One smoke test is not a stress test.** Smoke runs prove that the path works. They
do not produce a latency distribution, and they tell you nothing about capacity.

### 7.2 Playwright

* Look at passed, failed, flaky and interrupted counts, the duration of each test and
  each step, and traces and screenshots on failure.
* `results.json` holds the same information in machine-readable form, including
  `startTime` and `duration` for each run.

### 7.3 What counts as a pass

This repository has no agreed pass or fail criteria for capacity. The thresholds in
section 6.3 are suggestions. Record observations and decisions, not an unqualified
"pass".

### 7.4 Comparison table

| Target | Scenario | Users | Duration | Completed requests | Failure rate | p50 | p95 | Throughput | Observations | Report path | Decision |
|---|---|---:|---|---:|---:|---:|---:|---:|---|---|---|
| | | | | | | | | | | | |
| | | | | | | | | | | | |
| | | | | | | | | | | | |
| | | | | | | | | | | | |
| | | | | | | | | | | | |
| | | | | | | | | | | | |
| | | | | | | | | | | | |
| | | | | | | | | | | | |

---

## 8. Limits and presentation notes

Say these out loud when presenting:

* **Local runner, deployed target.** Locust and Playwright run on this laptop but
  target the deployed dev App and serving endpoint. Every figure includes the network
  path from the laptop, including VPN. Compare runs made from the same machine only.
* **One identity.** Every Locust user shares one OAuth token, and every browser
  context shares one saved session. Several virtual users are several **sessions**
  under **one real identity**.
* **Not validated:** permissions across users, several on-behalf-of (OBO) identities,
  or limits that apply per user. `/api/healthz` reports `auth_mode` (`obo` or
  `pat_fallback`), but only for this one caller.
* **Different paths:**
  * UI (Playwright): browser, React, Apps proxy, BFF, `/api/chat/stream`, then the
    agent.
  * BFF (Locust): Apps proxy, BFF (`/api/chat` blocking, or `/api/chat/stream`),
    then the agent.
  * Serving (Locust): Model Serving, then the agent. This bypasses the UI, the proxy
    and the BFF.
* **Cost and data.** Business steps start LLM, Genie/SQL and serving work, and may
  store conversations. Locust's BFF sessions are plain UUIDs with no test prefix.
  Serving sessions carry `BIC_SESSION_ID_PREFIX`, which defaults to `load_test`.
* **Cleanup.** Only remove data that clearly belongs to the test, and only through
  supported methods. `openapi.json` defines `DELETE /api/historical-query`, which
  deletes one query in a session the caller owns, identified by `session_id` and
  `user_query_id`. The repository has no cleanup script, and Locust does not record
  those IDs (Gap G5). This runbook has not verified any cleanup method for sessions
  created through direct serving calls. Ask the App owner rather than deleting data by
  hand.

---

## 9. Short technical-demo sequence

This is the smallest set of tests that shows every layer, and takes about 15 to 20
minutes. Refresh the browser session **before** the audience arrives.

| # | Terminal | Step | What it shows |
|---|---|---|---|
| 1 | A | 1.1 Enter the repository; 1.2 toolchain check | The tools are installed |
| 2 | A | 1.4 Get the token; 1.5 presence check | OAuth U2M is working; no secrets on screen |
| 3 | B | 1.7 Browser-session check (1.8 if needed) | The separate browser credential |
| 4 | A | **Step 1.1** Deployed health smoke | The App is reachable and authenticated |
| 5 | A | 1.6 Set the user ID; **Step 2.1** Serving `Hello` | The direct endpoint contract works |
| 6 | B | **Step 3.2** UI smoke | The authenticated UI renders |
| 7 | B | **Step 3.3** Chat journey, headed | End-to-end business answer, streamed and rendered |
| 8 | A and B | **Stage 4** combined (5 users plus 1 journey) | The UI keeps working under modest backend load |
| 9 | A and B | Open both reports | Where the evidence is stored |

---

## 10. Extended load and stress sequence

Run this only within an agreed dev budget, and review the result after every step.

1. Preparation: steps 1.1 to 1.8.
2. BFF: step 1.1, then 1.2, 1.3, 1.4, 1.5 and 1.6. Optionally add 1.7 (streaming).
3. Serving: step 2.1, then 2.2, 2.3, and the 2.4 stages in order.
4. UI: step 3.2, then 3.3, 3.4, and optionally 3.5.
5. Combined: Stage 4.
6. Stress: sections 6.1 and 6.2, then one step 6.4 stage at a time, stopping at the
   first degraded stage or at the budget.
7. Recovery: section 6.5.
8. Record the results: sections 6.6 and 7.4.

---

## 11. Command quick reference

All commands run in `C:\Projects\bic-load-testing`. Create a new `$Out` before each
run (section 1.3).

```powershell
# Token (Terminal A)
.\scripts\get-databricks-token.ps1 -WorkspaceHost https://adidas-dwhm-lh-wrk-gazelle-dev.cloud.databricks.com
if ($env:BIC_AUTH_TOKEN) { "set (length=$($env:BIC_AUTH_TOKEN.Length))" } else { "NOT set" }
(databricks auth token --host https://adidas-dwhm-lh-wrk-gazelle-dev.cloud.databricks.com | ConvertFrom-Json).expiry
$env:BIC_TEST_USER_ID = (Invoke-RestMethod -Uri "https://adidas-dwhm-lh-wrk-gazelle-dev.cloud.databricks.com/api/2.0/preview/scim/v2/Me" -Headers @{ Authorization = "Bearer $env:BIC_AUTH_TOKEN" }).userName

# Browser session (Terminal B)
.venv\Scripts\python.exe -c "from control_centre.auth import inspect_storage_state as i; s=i(app_url='https://ds-insights-companion-ui-809065969263152.aws.databricksapps.com'); print(s.status_text, s.app_session_expiry)"
npx playwright codegen --save-storage=playwright/.auth/bic-user.json "https://ds-insights-companion-ui-809065969263152.aws.databricksapps.com"

# Output folder
$Out = Join-Path $PWD "results\cli\$(Get-Date -Format yyyyMMdd-HHmmss)-<label>"; New-Item -ItemType Directory -Path $Out | Out-Null

# Locust - report flags appended to every run
#   --csv "$Out\locust" --csv-full-history --html "$Out\locust.html"
.venv\Scripts\locust.exe --config config/locust.deployed-smoke.conf  <report flags>
.venv\Scripts\locust.exe --config config/locust.deployed-stress.conf -u <N> -r <R> -t <T> --stop-timeout 180 <report flags>
.venv\Scripts\locust.exe --config config/locust.deployed-stream.conf --stop-timeout 180 <report flags>
.venv\Scripts\locust.exe --config config/locust.serving-smoke.conf <report flags>
.venv\Scripts\locust.exe --config config/locust.serving-stress.conf -u <N> -r <R> -t <T> --stop-timeout 190 <report flags>
Invoke-Item "$Out\locust.html"

# Playwright - set these before every run
$env:PLAYWRIGHT_HTML_OUTPUT_DIR = "$Out\html-report"; $env:PLAYWRIGHT_JSON_OUTPUT_NAME = "$Out\results.json"; $env:PLAYWRIGHT_HTML_OPEN = "never"
npx playwright test tests/bic-smoke.spec.ts --project=chromium --workers=1 --output "$Out\artifacts" --reporter "list,html,json"
npx playwright test tests/bic-chat-complete.spec.ts --project=chromium --headed --workers=1 --output "$Out\artifacts" --reporter "list,html,json"
npx playwright test tests/bic-chat-complete.spec.ts --project=chromium --repeat-each=3 --workers=1 --output "$Out\artifacts" --reporter "list,html,json"
npx playwright show-report "$Out\html-report"
npx playwright show-trace "<path>\trace.zip"

# Serving question switch
$env:BIC_TEST_QUESTION = 'How many articles do we have in Training KCC for SS27?'
Remove-Item Env:BIC_TEST_QUESTION -ErrorAction SilentlyContinue
```

---

## 12. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Playwright fails on `not.toHaveURL(...login...)`, or times out waiting for **New Session** or `WELCOME TO IRIS`; the screenshot shows Databricks sign-in | The saved browser session has expired or been revoked | Step 1.8, then step 1.7, then step 3.2 |
| Step 1.7 prints `App session expired`, `No app session` or `Missing` | The saved session is expired, incomplete or missing | Step 1.8 |
| Locust reports `unexpected status 401` on every request | `BIC_AUTH_TOKEN` is missing, expired, or was set in a **different window** | Step 1.5 in the Locust window, then step 1.4, then restart the run |
| 401 errors begin partway through a long run | The token expired during the run; the scenarios never refresh it | Check the expiry before each long stage (step 1.4). Discard the stage as an authentication failure. |
| 403 errors | The identity lacks permission on the App or endpoint | Ask the owner. Not a load issue. |
| `databricks auth token` fails with `databricks OAuth is not configured for this host` | A PAT profile was selected, not a U2M login | Run `databricks auth login --host <workspace>`, or the helper script |
| The helper script fails because running scripts is disabled | PowerShell execution policy | See step 1.1 |
| `RuntimeError: BIC_TEST_USER_ID must be set...` | Step 1.6 was skipped | Step 1.6 |
| `databricks current-user me`: `Error: unknown flag: --host` | In CLI v1.4.0, `current-user me` accepts only `--profile` | Use the `Invoke-RestMethod ... /scim/v2/Me` command in step 1.6 |
| `Could not find '<file>'` or a config file error | Wrong working directory or mistyped path | `Set-Location C:\Projects\bic-load-testing`, then check with `Get-ChildItem config\locust.*.conf` |
| `ModuleNotFoundError: locust`, or `locust.exe` not found | The virtual environment is missing | `uv venv --python 3.12` then `uv pip install -r requirements.txt` |
| Chromium executable not found | The Playwright browser is not installed | `npx playwright install chromium` |
| A BFF Locust run appears stuck at the end | A `/api/chat` call is still in flight. The BFF scenarios have no client timeout, and `--stop-timeout 180` is waiting. | Wait up to 180 s, or press Ctrl+C once. Record it as a slow or hung request. |
| The serving run times out after 180 s | The endpoint is slower than `BIC_REQUEST_TIMEOUT_SECONDS` | Record it as a timeout. Raise `BIC_REQUEST_TIMEOUT_SECONDS` only as a deliberate, recorded decision. |
| The serving smoke test sits idle for about 200 s | Expected behaviour (step 2.1) | Press Ctrl+C once after the request is recorded |
| The chat journey times out at 120 s during load | The test's own `test.setTimeout(120_000)` | Record it as degraded responsiveness (Gap G4) |
| `npx playwright show-report` shows an old run | No folder was given, so it opened the default `playwright-report/` | Pass the folder: `npx playwright show-report "$Out\html-report"` |
| The report is missing after a run | `$Out` was reset or the window was closed; Ctrl+C was pressed twice during report writing; or Locust was killed before writing | `Get-ChildItem results\cli \| Sort-Object Name \| Select-Object -Last 10`. Press Ctrl+C only once. |
| `New-Item` error that the folder already exists | Two runs started in the same second | Run the `$Out` line again |
| Playwright blocks the terminal after a failure, serving the report | `PLAYWRIGHT_HTML_OPEN` is not set in this window | Press Ctrl+C, then set `$env:PLAYWRIGHT_HTML_OPEN = "never"` |
| `npx playwright test` also runs `bic-chat-recorded.spec.ts` | No spec file was given | Always pass the spec path |

---

## 13. Code gaps that affect this runbook

None of these gaps prevents the documented sequence from running. They limit what the
results can show. Each fix below is the smallest change that would close the gap;
none has been made.

| ID | Gap | Effect | Smallest change |
|---|---|---|---|
| **G1** | `basic_scenario.py` and `stream_scenario.py` accept `action == "error"` as a valid `ChatResult`. The allowed set includes `"error"`, and the stream check only looks at the required keys. | A chat turn that ends in an agent or orchestration error still shows as **passed** in Locust. BFF business failure rates can be understated. | In `_is_valid_chat_result` and in the stream success check, treat `action == "error"` as a failure. Optionally, also require a non-empty `message` or `insighter` for `summarized` and `return_response`. |
| **G2** | The BFF scenarios pass no `timeout=` to `/api/chat`, `/api/chat/stream` or the other calls, and Locust's `HttpSession` has no default timeout. | A hung request is never recorded as a timeout. Users can block until `--stop-timeout` kills them, and those requests may not be recorded at all. | Add `timeout=` to the BFF calls, for example by reusing the `BIC_REQUEST_TIMEOUT_SECONDS` pattern from the serving scenarios. |
| **G3** | `smoke_healthz.py` checks only for HTTP 200. `HealthzResponse.ok` is not checked. | A 200 response with `ok: false` passes the gate. | Parse the JSON and fail when `ok` is not `true`. `basic_scenario._is_valid_healthz` shows the shape; it also checks only that `ok` is a boolean. |
| **G4** | `bic-chat-complete.spec.ts` sets `test.setTimeout(120_000)` inside the test, so a `--timeout` value on the command line is ignored. | Under load, journeys longer than 120 s fail as timeouts, and the test cannot be given more time without editing it. | Read the limit from an environment variable, defaulting to 120000, or move it to the config. |
| **G5** | No test-data tagging or cleanup for BFF runs. Session IDs are plain `uuid4` values, and `session_id` and `user_query_id` are not recorded. | Conversations created by load tests cannot be reliably identified or removed through `DELETE /api/historical-query`. | Optionally prefix the BFF session IDs, if the BFF accepts client-chosen IDs up to 128 characters as the spec allows, and log the ID pairs to a file under `$Out`. |
| **G6** | Tokens are read once per virtual user and never refreshed. | Runs longer than the token's lifetime fail with 401. | Operational workaround: check the expiry before each stage (step 1.4). A code fix would need a token-refresh mechanism, which is out of scope. |
| **G7** | The serving smoke test stops its user but not the Locust process. | The run sits idle for 200 s. | Raise `StopTest` or call `self.environment.runner.quit()` after the single request, or lower `run-time` in `config/locust.serving-smoke.conf`. |
| **G8** | The serving scenarios do not check the content of the answer beyond "non-empty output with no error item". | A generic or irrelevant answer still passes. | Answer quality is out of scope for load tests. Check a known business question with the Playwright journey instead. |
| **G9** | `stream_scenario.py` always uses one fixed question and opens a new conversation on every request. | This is not a multi-turn scenario, and there is no variety in questions. | Acceptable for timing. If needed, reuse `SAMPLE_QUESTIONS` from `basic_scenario.py`. |

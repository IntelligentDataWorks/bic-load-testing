# BIC Load Testing

Locust load/stress tests for the DS Insights Companion FastAPI BFF (modeled directly
from [openapi.json](openapi.json)), Playwright UI tests against the deployed React
app, and a local Streamlit control centre that runs and reviews all of them.

> **New here? Start with [docs/RUNBOOK.md](docs/RUNBOOK.md).** It lists every
> prerequisite, the one-time setup, how to sign in, how to test user sessions from the
> Streamlit app, a 15-minute demo script, and a ready-to-paste GitHub Copilot setup prompt.

## Streamlit control centre (recommended entry point)

```powershell
uv venv --python 3.12
uv pip install -r requirements.txt
npm install
npx playwright install chromium
.venv\Scripts\streamlit.exe run streamlit_app.py
```

Everything below can also be done from the UI: profile selection with safe
per-run overrides, Databricks OAuth U2M sign-in, preflight checks, live logs, a
safe stop, parsed Locust and Playwright results, report opening/downloading, and
an LLM diagnosis of a completed run.

- [docs/RUNBOOK.md](docs/RUNBOOK.md) -- start here: prerequisites, setup, user-session testing, demo script.
- [docs/streamlit-control-centre.md](docs/streamlit-control-centre.md) -- architecture, auth, discovery, workflows, secret handling, troubleshooting, limitations.
- [docs/cli-reference.md](docs/cli-reference.md) -- every test run from PowerShell without the app, plus stress escalation.
- [docs/playwright-setup-and-demo.md](docs/playwright-setup-and-demo.md) -- the underlying Playwright commands and recording new journeys.

The sections below document the direct CLI workflow, which still works unchanged.

## Project layout

```
streamlit_app.py       Streamlit control centre entry point
app_state.py           session state, run registry, cached toolchain probes
ui_components.py       shared Streamlit fragments
app_pages/             one file per page (dashboard, configure, run, results, ...)
control_centre/        all backend logic, importable without Streamlit
tools/render_check.py  headless render check for every page
scenarios/
  auth.py               shared TokenAuthHttpUser base (reads BIC_AUTH_TOKEN, optional)
  basic_scenario.py      BicApiUser: health/healthz/me/data-sources/sessions + chat flow
  approved_question_scenario.py  ApprovedQuestionUser: approved questions, one new session per journey
  chat_outcome.py        business verdict for a chat turn (HTTP 200 is not an answer)
  smoke_healthz.py       HealthzSmokeUser: single /api/healthz check, used as a gate
  stream_scenario.py     BicApiStreamUser: POST /api/chat/stream (measured separately)
  serving_endpoint_smoke.py  one direct, non-streaming serving-endpoint invocation
  serving_endpoint_load.py   sustained invocations of the same serving endpoint
config/
  locust.conf                 local, no-auth defaults (mirrors root locust.conf)
  locust.local-smoke.conf     1 user, /api/healthz only, against a local BFF
  locust.local-stream.conf    1 user, /api/chat/stream, against a local BFF
  locust.deployed-smoke.conf  1 user, /api/healthz only, against the deployed app
  locust.deployed-stream.conf 1 user, /api/chat/stream, against the deployed app
  locust.deployed-stress.conf full load test, against the deployed app
  locust.deployed-approved.conf approved-question chat load (set BIC_WORKLOAD_IDS for the mix)
  locust.serving-smoke.conf   1 direct serving-endpoint invocation
  locust.serving-stress.conf  sustained serving-endpoint load
  locust.prod-serving-smoke.conf 1 invocation of the PROD agent endpoint (gate)
  locust.prod-serving-load.conf  10 users on the PROD agent endpoint, data/prod_questions.txt
  .env.example                template for BIC_AUTH_TOKEN / BIC_ENABLE_FULL_FLOW
  app-settings.json           control-centre guardrails/thresholds (local, no secrets)
tests/                        Playwright specs (see docs/playwright-setup-and-demo.md)
tests/python/                 pytest unit tests for chat_outcome.py (python -m pytest tests/python -q)
playwright.config.ts          Playwright config; BIC_* env vars override its defaults
scripts/
  get-databricks-token.ps1    mints an OAuth U2M token into $env:BIC_AUTH_TOKEN
data/
  sample_questions.txt        chat questions used by basic_scenario.py
  approved_questions.txt      43 approved questions with IDs and domains (orchestrator.dev.yaml)
  prod_questions.txt          37 routing examples from orchestrator.prod.yaml (prod serving load)
results/                      generated CSV/HTML reports and results/<run-id>/ (gitignored)
locust.conf                   root copy of the local, no-auth default config
```

## Setup

```powershell
uv venv --python 3.12
uv pip install -r requirements.txt
```

## 1. Local, no-auth run against FastAPI directly

Uses the root `locust.conf` (host `http://localhost:8000`, no `BIC_AUTH_TOKEN` needed).
Start your local FastAPI BFF first, then:

```powershell
.venv\Scripts\locust.exe
```

This runs `BicApiUser` from [scenarios/basic_scenario.py](scenarios/basic_scenario.py): health, healthz,
me, data-sources, sessions, then (if `BIC_ENABLE_FULL_FLOW` isn't set to `false`) create/obtain
session, chat, session-chat, visualization.

## 2. Health smoke check (gate before any deployed load test)

Single user, single endpoint (`/api/healthz`). Run this first and confirm `0 failures`
before ever running the stress config.

```powershell
# against local FastAPI
.venv\Scripts\locust.exe -f scenarios/smoke_healthz.py --headless -u 1 -r 1 -t 10s --host http://localhost:8000

# against the deployed app (after loading BIC_AUTH_TOKEN, see step 4)
.venv\Scripts\locust.exe --config config/locust.deployed-smoke.conf
```

## 3. Stream scenario (`/api/chat/stream`)

Run separately from the basic scenario -- SSE timing isn't comparable to normal
request/response latency (see the docstring in the file).

```powershell
.venv\Scripts\locust.exe -f scenarios/stream_scenario.py --headless -u 1 -r 1 -t 10s --host http://localhost:8000
```

## 4. Connecting to Databricks (OAuth U2M) for the deployed app

The deployed app enforces auth, so requests need a bearer token. Do **not** use a
static PAT from `.databrickscfg` -- mint a short-lived OAuth U2M token instead:

```powershell
.\scripts\get-databricks-token.ps1 -WorkspaceHost https://adidas-dwhm-lh-wrk-gazelle-dev.cloud.databricks.com
```

This runs `databricks auth login --host <workspace>` (opens a browser once to sign in,
caches a refresh token via the Databricks CLI) and `databricks auth token --host <workspace>`
(returns a fresh access token), then exports it as `$env:BIC_AUTH_TOKEN` for the
**current PowerShell session only** -- it is never written to a file in this repo.

Then, in that same session:

```powershell
# 1. Gate: must show 0 failures before continuing
.venv\Scripts\locust.exe --config config/locust.deployed-smoke.conf

# 2. Only after the smoke check passes
.venv\Scripts\locust.exe --config config/locust.deployed-stress.conf
```

If the token expires during a long run, re-run `get-databricks-token.ps1` and restart
the test -- `databricks auth token` refreshes silently as long as the cached login is
still valid.

## Config reference

| File | Host | Auth | Users | Purpose |
|---|---|---|---|---|
| `locust.conf` / `config/locust.conf` | `localhost:8000` | none | 1 | local dev, no-auth |
| `config/locust.deployed-smoke.conf` | deployed app | `BIC_AUTH_TOKEN` | 1 | gate before stress |
| `config/locust.deployed-stress.conf` | deployed app | `BIC_AUTH_TOKEN` | 20 | actual load/stress run |
| `config/locust.serving-smoke.conf` | Databricks workspace | `BIC_AUTH_TOKEN` + `BIC_TEST_USER_ID` | 1 | single serving-endpoint invocation |
| `config/locust.serving-stress.conf` | Databricks workspace | `BIC_AUTH_TOKEN` + `BIC_TEST_USER_ID` | 5 | sustained serving-endpoint load |
| `config/locust.prod-serving-smoke.conf` | PROD workspace `adidas-lh-wrk-gazelle` | `BIC_AUTH_TOKEN` + `BIC_TEST_USER_ID` + `BIC_SERVING_ENDPOINT_PATH` | 1 | PROD serving-endpoint gate |
| `config/locust.prod-serving-load.conf` | PROD workspace `adidas-lh-wrk-gazelle` | same + `BIC_QUESTIONS_FILE` | 10 | PROD serving-endpoint load, 10 min |
| `config/locust.local-smoke.conf` | `localhost:8000` | none | 1 | local health gate |
| `config/locust.local-stream.conf` | `localhost:8000` | none | 1 | local SSE timing |
| `config/locust.deployed-stream.conf` | deployed app | `BIC_AUTH_TOKEN` | 1 | deployed SSE timing |

Environment variables (see [config/.env.example](config/.env.example)):

- `BIC_AUTH_TOKEN` -- bearer token forwarded as `Authorization: Bearer <token>`. Leave unset for local runs.
- `BIC_ENABLE_FULL_FLOW` -- defaults to `true`; set to `false` to skip create-session/chat/history/visualization and only run the read-only checks.
- `BIC_TEST_USER_ID` -- required by the serving-endpoint scenarios; the caller's Databricks user id/email.
- `BIC_TEST_QUESTION` -- optional; the user turn sent by the serving-endpoint scenarios (default `Hello`).
- `BIC_SERVING_ENDPOINT_PATH` -- optional; overrides `/serving-endpoints/ds-insights-companion-agent-dev/invocations`.
- `BIC_REQUEST_TIMEOUT_SECONDS` -- optional; serving-endpoint request timeout (default `180`).
- `BIC_SESSION_ID_PREFIX` -- optional; prefix for the per-request generated session id (default `load_test`).
- `BIC_QUESTIONS_FILE` -- optional, `serving_endpoint_load.py` only; an `id|domain|kind|question` file (e.g. `data/prod_questions.txt`). Questions are cycled across all users and each request is named `<endpoint> [<domain>]`.
- `BIC_RESULTS_JSONL` -- optional, `serving_endpoint_load.py` only; writes one sanitized line per invocation (question id, expected vs routed domain, orchestrator action, status, latency).

For the PROD agent endpoint set `BIC_SERVING_ENDPOINT_PATH=/serving-endpoints/ds-insights-companion-agent/invocations`
and a token for `https://adidas-lh-wrk-gazelle.cloud.databricks.com`, then run the prod smoke config before the prod load config.

Playwright reads these too, all optional, each falling back to the literal already in
[playwright.config.ts](playwright.config.ts): `BIC_BASE_URL`, `BIC_STORAGE_STATE`,
`BIC_TRACE`, `BIC_SCREENSHOT`, `BIC_VIDEO`.

Reports (CSV + HTML) are written to `results/` by every config above. Runs started
from the Streamlit app write to `results/<run-id>/` instead, so they never overwrite
each other.

## Troubleshooting

### `401` from the serving endpoint or the deployed app

Almost always means `BIC_AUTH_TOKEN` is missing or expired **in the shell that's running
locust** -- an env var set in one PowerShell window does not carry over to another window.
Set the token, then run locust, in the same window:

```powershell
.\scripts\get-databricks-token.ps1 -WorkspaceHost https://adidas-dwhm-lh-wrk-gazelle-dev.cloud.databricks.com
locust --config config/locust.serving-smoke.conf
```

If you can't tell whether the token is set, check its presence without printing it:

```powershell
if ($env:BIC_AUTH_TOKEN) { "set (length=$($env:BIC_AUTH_TOKEN.Length))" } else { "NOT set" }
```

The Streamlit control centre does not have this problem: it runs `databricks auth token`
itself, keeps the result in session memory, and injects it into each test subprocess's
own environment. Use **Authentication -> Get token** there instead.

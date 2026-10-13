# BIC Load Testing

Locust load/stress tests for the DS Insights Companion FastAPI BFF (modeled directly
from [openapi.json](openapi.json)), Playwright UI tests against the deployed React
app, and a local Streamlit control centre that runs and reviews all of them.

> **New here? Start with [docs/RUNBOOK.md](docs/RUNBOOK.md) on Windows, or
> [docs/RUNBOOK-mac.md](docs/RUNBOOK-mac.md) on a Mac.** Each covers prerequisites,
> setup, sign-in, the first smoke checks, session tests and a demo script. Node.js and
> Playwright are only needed for the React UI tests.
> Using GitHub Copilot? Open the folder in VS Code and type **`/bic-playbook`** in
> Copilot Chat (Agent mode). It runs the setup for you and asks for anything missing.

## Documentation

| Doc | Use it to |
|---|---|
| [docs/RUNBOOK.md](docs/RUNBOOK.md) | **Start here on Windows.** Set up, start the app, sign in, run tests, read results, troubleshoot |
| [docs/RUNBOOK-mac.md](docs/RUNBOOK-mac.md) | **Start here on a Mac.** The same guide with macOS commands |
| [docs/streamlit-control-centre.md](docs/streamlit-control-centre.md) | Understand the app's internals: architecture, auth, discovery, secret handling, extending it |
| [docs/cli-reference.md](docs/cli-reference.md) | Run every test from Windows PowerShell without the app, including local no-auth runs and stress escalation |
| [docs/playwright-recording.md](docs/playwright-recording.md) | Record a new Playwright journey with Codegen |
| [.github/copilot-instructions.md](.github/copilot-instructions.md) | Rules Copilot follows in this repository |
| [reports/](reports/) | Results of past test campaigns |

## Project layout

```
streamlit_app.py       Streamlit control centre entry point
app_state.py           session state, run registry, cached toolchain probes
ui_components.py       shared Streamlit fragments
app_pages/             one file per page (dashboard, configure, run, results, ...)
control_centre/        all backend logic, importable without Streamlit
tools/render_check.py  headless render check for every page
app.yaml               Databricks Apps entry point for the control centre
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
  locust.*.conf               Locust profiles (see the table below)
  .env.example                template for the command-line workflow only
  app-settings.json           control-centre guardrails/thresholds (created locally, gitignored)
tests/                        Playwright specs
tests/python/                 pytest unit tests for chat_outcome.py
playwright.config.ts          Playwright config; BIC_* env vars override its defaults
scripts/
  get-databricks-token.ps1    mints an OAuth U2M token into $env:BIC_AUTH_TOKEN (CLI workflow)
data/
  sample_questions.txt        chat questions used by basic_scenario.py
  approved_questions.txt      43 approved questions with IDs and domains (orchestrator.dev.yaml)
  prod_questions.txt          37 routing examples from orchestrator.prod.yaml (prod serving load)
docs/                         runbook and reference docs
reports/                      test campaign reports
.github/                      Copilot instructions and the /bic-playbook prompt
results/                      generated reports, one results/<run-id>/ per run (gitignored)
locust.conf                   root copy of config/locust.conf (local, no auth)
```

## Locust profiles

The control centre lists every profile on **Configure test**. From PowerShell, run one
with `.venv\Scripts\locust.exe --config <file>` (see [docs/cli-reference.md](docs/cli-reference.md));
on a Mac, `.venv/bin/locust --config <file>`.

| Profile (`config/locust.<name>.conf`) | Scenario | Target | Needs | Users | Purpose |
|---|---|---|---|---:|---|
| `local` (also root `locust.conf`) | `basic_scenario.py` | `localhost:8000` | - | 1 | local BFF, no auth |
| `local-smoke` | `smoke_healthz.py` | `localhost:8000` | - | 1 | local health gate |
| `local-stream` | `stream_scenario.py` | `localhost:8000` | - | 1 | local SSE timing |
| `deployed-smoke` | `smoke_healthz.py` | DEV app | token | 1 | gate before any deployed load |
| `deployed-stream` | `stream_scenario.py` | DEV app | token | 1 | deployed SSE timing |
| `deployed-stress` | `basic_scenario.py` | DEV app | token | 20 | multi-turn load/stress |
| `deployed-approved` | `approved_question_scenario.py` | DEV app | token; optional `BIC_WORKLOAD_IDS` | 1 | approved-question chats; new session per journey plus history isolation check |
| `serving-smoke` | `serving_endpoint_smoke.py` | DEV workspace | token + `BIC_TEST_USER_ID` | 1 | one direct serving-endpoint invocation |
| `serving-stress` | `serving_endpoint_load.py` | DEV workspace | token + `BIC_TEST_USER_ID` | 5 | sustained serving-endpoint load |
| `prod-serving-smoke` | `serving_endpoint_smoke.py` | **PROD** workspace | PROD token + `BIC_TEST_USER_ID` + `BIC_SERVING_ENDPOINT_PATH` | 1 | PROD agent gate (**approval required**) |
| `prod-serving-load` | `serving_endpoint_load.py` | **PROD** workspace | same + `BIC_QUESTIONS_FILE` | 10 | PROD agent load, 10 min (**approval required**) |

DEV app: `https://ds-insights-companion-ui-809065969263152.aws.databricksapps.com`.
DEV workspace: `https://adidas-dwhm-lh-wrk-gazelle-dev.cloud.databricks.com`.
PROD workspace: `https://adidas-lh-wrk-gazelle.cloud.databricks.com`. For PROD, set
`BIC_SERVING_ENDPOINT_PATH=/serving-endpoints/ds-insights-companion-agent/invocations`
and use a token for the PROD workspace.

"Token" means a Databricks OAuth token: the app gets one on **Authentication**, and
the command line uses `scripts/get-databricks-token.ps1`.

## Environment variables

The control centre sets these per run from the **Scenario environment** form. On the
command line, set them in the PowerShell window that runs Locust
(template: [config/.env.example](config/.env.example)).

- `BIC_AUTH_TOKEN` -- bearer token forwarded as `Authorization: Bearer <token>`. Leave unset for local runs. Never store a real value in a file.
- `BIC_ENABLE_FULL_FLOW` -- defaults to `true`; set to `false` to skip create-session/chat/history/visualization and only run the read-only checks.
- `BIC_TEST_USER_ID` -- required by the serving-endpoint scenarios; your Databricks login email (the same identity as the token).
- `BIC_WORKLOAD_IDS` -- optional, `approved_question_scenario.py` only; comma-separated question IDs such as `Q01,Q02`. Empty cycles through all questions.
- `BIC_TEST_QUESTION` -- optional; the user turn sent by the serving-endpoint scenarios (default `Hello`).
- `BIC_SERVING_ENDPOINT_PATH` -- optional; overrides `/serving-endpoints/ds-insights-companion-agent-dev/invocations`.
- `BIC_REQUEST_TIMEOUT_SECONDS` -- optional; serving-endpoint request timeout (default `180`).
- `BIC_SESSION_ID_PREFIX` -- optional; prefix for the per-request generated session id (default `load_test`).
- `BIC_QUESTIONS_FILE` -- optional, `serving_endpoint_load.py` only; an `id|domain|kind|question` file (e.g. `data/prod_questions.txt`). Questions are cycled across all users and each request is named `<endpoint> [<domain>]`.
- `BIC_RESULTS_JSONL` -- optional, `serving_endpoint_load.py` only; writes one sanitized line per invocation (question id, expected vs routed domain, orchestrator action, status, latency).

Playwright reads these too, all optional, each falling back to the literal already in
[playwright.config.ts](playwright.config.ts): `BIC_BASE_URL`, `BIC_STORAGE_STATE`,
`BIC_TRACE`, `BIC_SCREENSHOT`, `BIC_VIDEO`.

Runs started from the control centre write to `results/<run-id>/`, so they never
overwrite each other. Profiles run from the command line write to the `csv`/`html`
paths in the `.conf` file unless you override them.

## Developing

Adding profiles, scenarios and Playwright specs, and the checks to run after a change:
[docs/streamlit-control-centre.md](docs/streamlit-control-centre.md) sections 13 to 17.

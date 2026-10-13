<!-- Maintainers: docs/RUNBOOK-mac.md is the macOS copy of this guide, with the same
section numbers. Keep sections 5 to 11 identical in both files. -->

# BIC Load Testing: Runbook (Windows)

**Start here.** This guide takes you from a fresh Windows laptop to running load and
user-session tests against the IRIS (DS Insights Companion) DEV app, using the local
Streamlit control centre. Setup takes about 15 minutes.

> **On a Mac?** Use [RUNBOOK-mac.md](RUNBOOK-mac.md) instead.

> **Let GitHub Copilot do it.** Open this folder in VS Code, open Copilot Chat in
> **Agent** mode and type **`/bic-playbook`**. Copilot follows this runbook, asks you for
> anything it needs, and stops when a step needs you in the browser. See
> [section 10](#10-set-up-with-github-copilot).

What the tool does:

* **Locust** sends API traffic (many simulated users) to the deployed IRIS backend
  or straight to the agent serving endpoint.
* **Playwright** drives a real Chromium browser through the IRIS UI, the way a user would.
* **The Streamlit control centre** wraps both. You pick a test, press **Start run**,
  and read the results. You don't need to type any Locust or Playwright commands.

Everything runs **on your laptop**. The targets are deployed Databricks DEV services.

---

## Contents

1. [Prerequisites](#1-prerequisites)
2. [Get the code](#2-get-the-code)
3. [One-time setup](#3-one-time-setup)
4. [Start the app](#4-start-the-app)
5. [Sign in (two separate credentials)](#5-sign-in-two-separate-credentials)
6. [First run: smoke checks](#6-first-run-smoke-checks)
7. [Testing user sessions](#7-testing-user-sessions)
8. [Reading results](#8-reading-results)
9. [15-minute demo script](#9-15-minute-demo-script)
10. [Set up with GitHub Copilot](#10-set-up-with-github-copilot)
11. [Safety rules](#11-safety-rules)
12. [Troubleshooting](#12-troubleshooting)
13. [Other docs](#13-other-docs)

---

## 1. Prerequisites

### Software

| Tool | Needed for | Minimum version (tested) | Check | Install (if missing) |
|---|---|---|---|---|
| Windows 10/11 with PowerShell | Everything | - | - | - |
| Git | Everything | any | `git --version` | `winget install Git.Git` |
| uv (Python package manager) | Everything | any (0.11) | `uv --version` | `winget install astral-sh.uv` |
| Python | Everything | 3.12 | `py -3.12 --version` | Not needed if you have `uv`: setup downloads Python 3.12 for you |
| Databricks CLI | Signing in to the deployed DEV services | v0.200 (v1.4.0) | `databricks --version` | `winget install Databricks.DatabricksCLI` |
| Node.js and npm | **React UI and Combined tests only** | Node 20 (Node 24.17, npm 11.13) | `node --version`, `npm --version` | `winget install OpenJS.NodeJS.LTS` |

**Already installed?** Keep it if it meets the minimum version; nothing is reinstalled.
If it's older, upgrade it with the tool you installed it with (for example
`winget upgrade OpenJS.NodeJS.LTS`). The old Python-based Databricks CLI (version 0.18
or lower) doesn't work; install the current one.

After installing anything, **restart VS Code** (or open a new PowerShell window outside
VS Code) so the updated `PATH` is picked up. If `winget` is blocked on your laptop,
install the same tools from your company software portal.

### Which tests do you need?

| You want to run | Node.js and Playwright |
|---|---|
| **FastAPI BFF** and **Serving endpoint** tests only (Locust, API traffic) | **Not needed.** Skip the Node.js row above, section 3.2 and section 5.2. |
| **React UI** or **Combined** tests too (Playwright, a real browser) | Needed. Follow every step. |

You can add the UI setup later at any time (section 3.2).

### Access

| You need | Used for | How to check |
|---|---|---|
| Read access to `https://github.com/IntelligentDataWorks/bic-load-testing` (private) | Cloning the code | The repository page opens when you are signed in to GitHub |
| A login to the DEV Databricks workspace `https://adidas-dwhm-lh-wrk-gazelle-dev.cloud.databricks.com` | Every test | You can sign in in a browser |
| Permission to use the IRIS DEV app `https://ds-insights-companion-ui-809065969263152.aws.databricksapps.com` | UI and BFF tests | The URL opens and shows **WELCOME TO IRIS** |
| `CAN QUERY` on the serving endpoint `ds-insights-companion-agent-dev` | Serving-endpoint tests only | Smoke check 3 in section 6 passes |
| Corporate network or VPN, if your workspace requires it | Reaching the workspace | The URLs above load |

If the GitHub repository or the IRIS URL doesn't open for you, ask the project owner for
access before you continue. Nothing else in this guide works without it.

### What you do *not* need

* **No Databricks PAT.** Sign-in uses Databricks OAuth in the browser (section 5.1).
* **No manual `~/.databrickscfg` editing.** The first sign-in creates the profile for you.
* **No `.env` file.** The app keeps your token in memory. `config/.env.example` is
  only for the command-line workflow.

---

## 2. Get the code

```powershell
git clone https://github.com/IntelligentDataWorks/bic-load-testing.git C:\Projects\bic-load-testing
Set-Location C:\Projects\bic-load-testing
```

Any folder works; the commands below assume this one. If Git asks you to sign in, use
the GitHub account that has access to the `IntelligentDataWorks` organisation.

---

## 3. One-time setup

Run everything in this section in PowerShell, from the folder you cloned into.

### 3.1 Python environment (everyone)

```powershell
uv venv --python 3.12
uv pip install -r requirements.txt
```

No `uv`? Use plain Python 3.12 instead:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 3.2 Playwright and Chromium (UI tests only)

Skip this if you only need FastAPI BFF and Serving endpoint tests.

```powershell
npm install
npx playwright install chromium
```

### 3.3 Verify the setup

Every command should print a version or `ok`:

```powershell
.venv\Scripts\python.exe --version          # Python 3.12.x
.venv\Scripts\locust.exe --version          # locust 2.x
.venv\Scripts\streamlit.exe version         # Streamlit, version 1.57 or later
databricks --version                        # Databricks CLI v1.x
npx playwright --version                    # UI tests only: Version 1.63 or later
.venv\Scripts\python.exe tools\render_check.py   # every page prints "ok", errors=0
```

`render_check.py` opens every page of the app headlessly. It takes about 15 seconds,
and "missing ScriptRunContext" warnings in its output are normal.

You don't need to activate the virtual environment. Every command here calls
`.venv\Scripts\...` directly, so PowerShell's script execution policy doesn't get in
the way.

**Skipped section 3.2?** The FastAPI BFF and Serving endpoint tests work normally.
The **Dashboard** shows Node.js, npm, Playwright and Chromium as failed; that is
expected and doesn't block those tests. You can't run **React UI** or **Combined**
tests or capture a browser session. To add them later, run section 3.2 and restart the
app.

Set up in the folder you'll keep using. If you move or rename the folder later,
delete `.venv` and repeat section 3.1.

---

## 4. Start the app

```powershell
.venv\Scripts\streamlit.exe run streamlit_app.py
```

Open <http://localhost:8501>. The app only listens on your own machine
(`127.0.0.1`), and **nothing runs until you press Start run**.

To check it's up from a second PowerShell window:

```powershell
(Invoke-WebRequest http://localhost:8501 -UseBasicParsing).StatusCode   # 200
```

To stop the app, press **Ctrl+C** in that PowerShell window. Your Databricks token
lives only in the app's memory, so after a restart you sign in again (section 5.1).

### The pages

| Page (sidebar) | Use it to |
|---|---|
| **Dashboard** | Check the toolchain is green, see the token and browser-session state, open recent runs |
| **Configure test** | Pick what to test, pick a profile or spec, adjust users and run time |
| **Authentication** | Get a Databricks token; capture the browser session |
| **Run test** | Review the target, the preflight checks and the command, then **Start run** |
| **Live logs** | Watch a run; **Stop this run** |
| **Results** | Metrics, pass/fail, reports and downloads for any run |
| **AI diagnosis** | Ask an LLM to summarise a finished run |
| **Run history** | Every past run and its settings |
| **Help & settings** | What each test proves; guardrails |

Every test follows the same flow:

**Configure test** → **Use this configuration** → **Run test** → **Start run** → **Live logs** → **Results**

---

## 5. Sign in (two separate credentials)

The two test tools sign in differently, and each credential expires on its own:

| Credential | Used by | Lifetime | Where it lives |
|---|---|---|---|
| Databricks OAuth token | Locust (API and serving tests) | About 1 hour; refresh in the app | App memory only, never on disk |
| Saved browser session | Playwright (UI tests only) | About 24 hours | `playwright/.auth/bic-user.json` (gitignored; never share it) |

### 5.1 Databricks token (for Locust tests)

**Authentication** → **Databricks OAuth U2M** tab:

1. Leave **Databricks CLI profile** empty and keep the DEV **Workspace host**.
2. Press **Start browser sign-in** and complete the sign-in in the browser that opens.
   You only need this the first time on a machine, or when the CLI login expires.
   The Databricks CLI saves an OAuth profile in `~/.databrickscfg` for you.
3. Press **Get token**.

**Expect:** a green **Authenticated** badge, an expiry countdown and a token *handle*.
The token itself is never shown. Press **Refresh token** when it gets close to expiry.

**Already have a `~/.databrickscfg`?** Leave the profile empty anyway. If you pick a
profile, it must show auth type `databricks-cli`. A PAT profile can't mint an OAuth
token (see Troubleshooting).

**PAT fallback (optional).** Only if OAuth isn't available to you: the **PAT** tab
accepts a PAT from a `~/.databrickscfg` profile or pasted into its password field. It
works for serving-endpoint tests, but the deployed IRIS app rejects it. Type a PAT
only into that field: never into a chat, a file or a commit.

### 5.2 Browser session (for Playwright tests)

UI tests only. Skip this if you skipped section 3.2.

**Authentication** → **Browser session** tab:

1. Press **Capture browser session**. A Chromium window and the Playwright Inspector open.
2. Complete the Databricks SSO sign-in and wait until IRIS shows **WELCOME TO IRIS**.
3. Close **both** the browser window and the Inspector. The file is only saved after both are closed.
4. Reload the page. **State** should read **Looks usable**.

Capture a new session on the day of any demo.

---

## 6. First run: smoke checks

Run these short checks to prove your setup works end to end. Each one takes under a
minute. If you skipped the UI setup (section 3.2), skip check 2.

| # | Check | On **Configure test** choose | Expect |
|---|---|---|---|
| 1 | The app is reachable and your token works | **FastAPI BFF** → profile `deployed-smoke` | Status `passed`; about 10 `GET /api/healthz` requests, 0 failures |
| 2 | The UI loads while signed in (**UI tests only**) | **React UI** → spec `bic-smoke.spec.ts` (turn **Headed** on to watch it) | `1 passed` |
| 3 | The agent endpoint answers (optional) | **Serving endpoint** → profile `serving-smoke`; set `BIC_TEST_USER_ID` to your Databricks login email | 1 request, 0 failures |

About check 3: the scenario sends one request and then waits out the profile's 200 s
run time. Once the request shows in **Live logs**, you can press **Stop this run**.
The report is still written.

If a check fails, see [Troubleshooting](#12-troubleshooting). The usual cause is an
expired token (check 1) or an expired browser session (check 2).

---

## 7. Testing user sessions

In IRIS, every conversation is a **session**. This repository tests sessions at three
levels: one real browser session, many API sessions in parallel, and sessions created
directly at the agent.

> **One identity.** Every simulated user and browser shares **your** Databricks login.
> 10 concurrent sessions means 10 conversations under one person, not 10 different
> people. Per-user permissions and per-user rate limits are not tested.

### Which test to pick

| Goal | On **Configure test** choose | What one session is | Pass signal |
|---|---|---|---|
| **A.** One real user session, end to end | **React UI** → `bic-chat-complete.spec.ts`, **Headed** on | The browser clicks **New Session**, asks a question, and waits for the streamed answer to appear | `1 passed` |
| **B.** The same journey, repeated | **React UI** → `bic-chat-complete.spec.ts`, **repeat-each** `3`, **Workers** `1` | Three new sessions, one after another | `3 passed` |
| **C.** Many sessions at once, isolation check | **FastAPI BFF** → `deployed-approved`; **Users** 1, then 5, then 10 | Every journey opens a new session, asks one approved business question, then reads the session history back | 0 failures on `/api/session-chat` |
| **D.** Long multi-turn sessions | **FastAPI BFF** → `deployed-stress`; **Users** 5 | Each simulated user keeps one conversation and adds turns for the whole run | 0 failures |
| **E.** One user's session while others load the system | **Combined** → Locust `deployed-approved` + Playwright `bic-chat-complete.spec.ts` | A + C at the same time | Playwright `1 passed`, Locust 0 failures |
| **F.** Agent sessions without the UI or backend | **Serving endpoint** → `serving-stress` | A new session for every request, ID `<prefix>_<uuid>` | 0 failures |

Start with **A**, then **C** with 1 user. Only add users once the previous run is clean.
**A**, **B** and **E** need the UI setup (section 3.2); **C**, **D** and **F** don't.

### A. One real user session (Playwright)

1. **Configure test** → **React UI** → **Playwright spec** `bic-chat-complete.spec.ts`.
2. Turn **Headed (visible browser)** on.
3. **Use this configuration** → **Run test** → **Start run**.

**Expect:** Chromium opens IRIS already signed in. It clicks **New Session**, types
`How many articles do we have in Training KCC for SS27?`, waits for
`/api/chat/stream` to finish, and checks that the answer appears on the page and the
URL contains `session=chat_...`. The result is `1 passed`.

The spec has its own 120-second limit, so the **Test timeout (ms)** field has no effect
on it. A timeout under load means the answer was slow, not that the UI is broken.

### C. Many sessions at once (Locust, approved questions)

This is the main session test. For each journey, a simulated user:

1. Opens a **new** session (`lt-<random id>`) and sends one question from
   `data/approved_questions.txt` to `POST /api/chat`.
2. Checks the **business** outcome, not only HTTP 200 (see the table below).
3. Calls `GET /api/session-chat` for that session and checks it holds **exactly one**
   record with **this** question. Anything else means sessions got mixed up or lost.

Steps:

1. **Configure test** → **FastAPI BFF** → **Profile** `deployed-approved`.
2. Set **Users** `1`, **Spawn rate** `1`, **Run time** `3m`.
3. Optional: in **Scenario environment**, set `BIC_WORKLOAD_IDS` to choose questions,
   for example `Q01,Q02,Q03`. Leave it empty to cycle through all 43 in order.
4. **Use this configuration** → **Run test**. Check the target banner shows the DEV
   app host and the preflight list is green, then press **Start run**.
5. When the run is clean, repeat with **Users** `5`, then `10`. Above 5 users you
   must type `RUN STRESS` to confirm.

How to read the rows on **Results**:

| Row | Meaning | Counted as failure when |
|---|---|---|
| `/api/chat` | Completed answers: a full data answer (`FULL_ANSWER`) or a valid direct reply (`VALID_DIRECT_RESPONSE`) | Refusal, application error, empty answer, timeout, invalid response, or the session ID returned doesn't match the one sent |
| `/api/chat [CLARIFICATION]`, `/api/chat [PARTIAL_ANSWER]` | The agent asked a follow-up question or answered only part of it. Valid behaviour, but not a finished journey | Never; it's listed separately so it doesn't hide in the answer latency |
| `/api/session-chat` | The isolation check | `session history mismatch`: the session didn't hold exactly this one question. **Stop and report this.** |

Each chat takes roughly 30 to 120 seconds, so a 3-minute single-user run gives only a
few samples. Chats still running when the run time ends are cut off and not counted.

### E. A user session under load (Combined)

1. **Configure test** → **Combined**.
2. **1. Load profile:** `deployed-approved`, **Users** `5`, **Run time** `5m`.
3. **2. UI journey:** `bic-chat-complete.spec.ts`, **Headed** on.
4. **3. Orchestration:** **Warm-up** `60` seconds, so chats are already running when
   the browser starts. Leave **Stop Locust when the UI journey finishes** off.
5. **Use this configuration** → **Run test** → **Start run**.

**Expect:** Live logs show `[locust]` lines, then `[playwright]` lines after the warm-up.
On **Results**, check the **Locust load** tab and the **Playwright journey** tab. Failures
in both at the same time overlap in time; that alone doesn't prove one caused the other.

---

## 8. Reading results

**Results** → pick the run (the latest is selected).

* **Locust:** total requests, failure %, median / p95 / p99, a table per endpoint and a
  load-over-time chart. A run with fewer than 20 requests is flagged: its percentiles
  are just one or two samples. Use **Open Locust report** or download the CSVs.
* **Playwright:** passed / failed / flaky, per-step timings, and screenshots and traces
  for failed tests. Use **Open HTML report**, or open a trace to replay the failure.
* **Files:** every run gets its own folder, `results/<run-id>/`, with `run.log`,
  `manifest.json` and the reports. Nothing is overwritten, and tokens are masked in the logs.

**AI diagnosis** (optional): press **Diagnose this run with AI** on **Results**. It
reuses the token you already hold. The default model endpoint is
`databricks-claude-sonnet-4-5`; if you can't query it, set another chat-model endpoint
on the **AI diagnosis** page. Open **Exactly what will be sent** to check the payload:
metrics only, with no tokens, headers, auth file or raw responses.

> Result files can contain real answers, SQL and query results. Keep them inside the team.

What the status codes mean:

| You see | It means |
|---|---|
| 401 or 403 | Token expired or missing, or no permission. **Not** a capacity result. Get a new token and re-run. |
| 429 | Throttling. A capacity signal, possibly a per-identity limit. |
| 5xx or timeouts | A server-side problem. Stop increasing load and tell the app owner. |

---

## 9. 15-minute demo script

The demo uses UI tests, so it needs the full setup including section 3.2. Before the
audience arrives: complete section 5 (token **and** browser session), and check the
**Dashboard** shows a green toolchain and **Looks usable**.

| # | Do | Point out |
|---|---|---|
| 1 | Open the **Dashboard** | The runner is local, the targets are the deployed DEV app and agent. Nothing runs until **Start run**. |
| 2 | **Authentication** → **Get token** | The app only shows a token *handle*, never the token. |
| 3 | Run `deployed-smoke` | The gate: auth works and the app is reachable before any load. |
| 4 | Run `serving-smoke` | Talks to the agent directly, bypassing UI and backend. Shows whether slowness is in the agent. |
| 5 | Run `bic-smoke.spec.ts`, **Headed** | A real browser, already signed in. A 200 from the API can't prove the UI renders; this can. |
| 6 | Run `bic-chat-complete.spec.ts`, **Headed** | The whole product path in one journey: browser, React, backend, streaming, agent. |
| 7 | Run `deployed-approved` with 5 users, 2 minutes | Five parallel sessions, each checked for a real answer and for an isolated history. |
| 8 | Run **Combined** (5 users + chat journey) | Locust answers "how much load", Playwright answers "is it still usable". |
| 9 | Open **Results** | Per-run folders, nothing overwritten, secrets masked in the log. |
| 10 | **Diagnose this run with AI** | Pass / Conditional Pass / Fail with an executive summary, based only on the metrics. |

Closing points:

* Load here is concurrency under **one** Databricks identity.
* Smoke runs prove the path works; they don't produce meaningful percentiles.
* If something breaks live, fall back to `deployed-smoke` and `bic-smoke.spec.ts`. They are the fastest checks that still cover the whole chain.

---

## 10. Set up with GitHub Copilot

### 10.1 Run the playbook

1. Clone the repository (section 2) and open the folder in VS Code.
2. Open Copilot Chat, switch to **Agent** mode, and type **`/bic-playbook`**.

The playbook is [.github/prompts/bic-playbook.prompt.md](../.github/prompts/bic-playbook.prompt.md).
Copilot also loads the repository rules in
[.github/copilot-instructions.md](../.github/copilot-instructions.md) automatically.
Together they make Copilot:

1. Ask whether you're on Windows or macOS, and whether you need React UI tests. It
   then follows only the runbook for your system ([RUNBOOK.md](RUNBOOK.md) for
   Windows, [RUNBOOK-mac.md](RUNBOOK-mac.md) for macOS), and skips Node.js,
   `npm install` and Chromium if you don't need UI tests.
2. Check every prerequisite in section 1 and ask before installing anything.
3. Run the setup and verification in section 3.
4. Start the app (section 4) and give you the URL.
5. Walk you through sign-in (section 5). This part needs you in the browser.
6. Walk you through the smoke checks (section 6) and explain the results.

It never starts a load test above 1 user, and never touches production, unless you
ask it to.

### 10.2 What Copilot will ask you

Copilot asks for these only when a step needs them. Have the answers ready:

| Copilot asks | When | Your answer |
|---|---|---|
| "Are you on Windows or macOS?" | First | Your system. Copilot then follows only that runbook. |
| "Do you need React UI tests?" | First | **Yes** for React UI or Combined tests. **No** for FastAPI BFF and Serving endpoint tests only; Copilot then skips Node.js, `npm install` and Chromium. |
| "May I install `<tool>`?" or "May I upgrade `<tool>`?" | A prerequisite is missing, or older than its minimum version | Yes or no. Restart VS Code after installs. A tool that already meets the minimum is left as it is. |
| "Can you open the DEV workspace and the IRIS URL in your browser?" | Before setup | If not, request access first (section 1) |
| "Complete the Databricks sign-in in the browser, then press **Get token**" | Section 5.1 | Sign in with your work account. No PAT is needed. |
| "Do you already have a `~/.databrickscfg` profile for the DEV workspace?" | Only if **Get token** fails | Say which auth type it shows. Copilot will not open the file. |
| "Capture the browser session" | Section 5.2, UI tests only | Do it in the app, then confirm **Looks usable** |
| "What is your Databricks login email?" | Smoke check 3 and other serving tests | Your work email. It goes into `BIC_TEST_USER_ID`. |
| "Confirm more than 5 users / this budget" | Any stress run | Confirm, and tell the app owner first (section 11) |

Copilot must never ask you to paste a token or PAT into the chat. If it does, refuse
and use the app's **Authentication** page instead.

Useful follow-up questions:

* "Using docs/RUNBOOK.md section 7, how do I test 10 concurrent sessions?"
* "My smoke test fails with 401. What does docs/RUNBOOK.md say to do?"
* "Explain what scenarios/approved_question_scenario.py checks."

---

## 11. Safety rules

* **DEV only.** The `prod-serving-*` profiles target production. Don't run them without
  explicit approval from the endpoint owner. The app warns when a host looks like production.
* **Start small.** Begin with 1 user and step up only after a clean run. Above 5 users
  the app asks you to type `RUN STRESS`. It caps runs at 50 users and 30 minutes.
* **Every chat costs money.** Each one runs LLM, SQL and serving work. Agree a budget and
  tell the app owner before any run with more than a few users.
* **Stopping a run** (sidebar **Stop run**, or **Stop this run** on Live logs) stops the
  client. Requests the server already accepted may still finish.
* **Never commit or share** these. `.gitignore` already excludes them; keep it that way:

  | Path | Why |
  |---|---|
  | `playwright/.auth/` | **Your live browser session cookies.** Anyone with this file can use IRIS as you. |
  | `results/`, `playwright-report/`, `test-results/` | Test output; can contain answers, SQL and query results |
  | `config/app-settings.json`, `.env`, `config/.env` | Local settings |
  | Any token or PAT | Grants access as you |

---

## 12. Troubleshooting

| Problem | Fix |
|---|---|
| `git clone` says `Repository not found` | Your GitHub account has no access, or Git used a different saved account. Ask the project owner for access, then sign in with the right account. |
| `uv`, `node`, `databricks` or `git` not found right after installing | Restart VS Code (or open a new PowerShell window) so `PATH` refreshes. |
| `npm install` or `npx playwright install chromium` fails with a network error | A corporate proxy blocks downloads. Ask IT for the proxy address and set `$env:HTTPS_PROXY` in that window, or connect to the VPN. |
| `401` on a deployed target | Token missing or expired. **Authentication** → **Get token** (or **Refresh token**), then re-run. After a Streamlit restart, you always need a new token. |
| **Run test** says `requires BIC_AUTH_TOKEN but no token is held` | Same as above: get a token first. |
| `databricks OAuth is not configured for this host` | A PAT profile was selected. Clear **Databricks CLI profile**, keep the workspace host, press **Start browser sign-in**, then **Get token**. |
| AI diagnosis says `No token held` | Get a token on **Authentication** (OAuth is enough; no PAT needed), then retry. |
| `403` | Your identity lacks permission on the app or endpoint. Ask the owner; it's not a load issue. |
| Playwright lands on a Databricks login page, or **Run test** says `Saved Playwright session for the app expired` | **Authentication** → **Browser session** → **Capture browser session**. |
| The browser session never shows **Looks usable** | Close **both** the browser and the Playwright Inspector after IRIS loads, then reload the page. |
| `RuntimeError: BIC_TEST_USER_ID must be set` | Serving tests need your Databricks login email in `BIC_TEST_USER_ID`. |
| Locust reports 0 requests | A required setting was empty and the scenario stopped at startup. Check the `RuntimeError` in **Live logs** or `results/<run-id>/run.log`. |
| A run shows `cancelled` immediately | Something interrupted the process. Check `results/<run-id>/run.log`. |
| `node` / `npx` not found in preflight | Only matters for UI tests. Install Node.js and run section 3.2, then restart Streamlit. Toolchain checks are cached for 10 minutes. |
| `Chromium` missing | Only matters for UI tests. Run `npx playwright install chromium`, then **Rescan repository** on the Dashboard. |
| A new `.conf` profile doesn't appear | **Dashboard** → **Rescan repository**. |
| "A run is already active" | Only one run at a time. Stop it from the sidebar or **Live logs**. |
| `streamlit.exe` / `locust.exe` not found, or `Fatal error in launcher` | The virtual environment is missing, or the folder was moved after setup. Delete `.venv` and repeat section 3.1. |
| `Port 8501 is already in use` | The app is already running in another window. Use that one, or press **Ctrl+C** there first. |
| The Playwright HTML report won't embed | It's a folder. Use **Launch playwright show-report** or download the zip. |

Command-line problems are covered in [cli-reference.md section 12](cli-reference.md#12-troubleshooting).

---

## 13. Other docs

| Doc | Read it when you want to |
|---|---|
| [RUNBOOK-mac.md](RUNBOOK-mac.md) | Set up and run on a Mac |
| [README.md](../README.md) | See the project layout, every Locust profile and every environment variable |
| [streamlit-control-centre.md](streamlit-control-centre.md) | Understand how the app works inside: architecture, discovery, secret handling, adding profiles and scenarios |
| [cli-reference.md](cli-reference.md) | Run Locust and Playwright from PowerShell without the app, plan a stress escalation, or dig into result interpretation |
| [playwright-recording.md](playwright-recording.md) | Record a new Playwright journey with Codegen |

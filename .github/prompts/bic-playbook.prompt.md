---
agent: 'agent'
description: 'Set up this repository on Windows, start the BIC load-testing control centre, and guide sign-in and the first smoke checks'
---

You are setting up this repository for a new teammate by following `docs/RUNBOOK.md`.
Read `docs/RUNBOOK.md` and `.github/copilot-instructions.md` first, and follow the
rules in `.github/copilot-instructions.md` throughout.

Work through the phases below in order. After each phase, tell the user in one or two
lines what passed and what comes next. Ask the user only the questions listed in
`docs/RUNBOOK.md` section 10.2, and only when a step needs the answer.

## Phase 1: Prerequisites (RUNBOOK section 1)

1. Run every **Check** command from the Software table. List anything missing or
   older than the tested version, with its install command.
2. Ask before installing each missing tool. After any install, tell the user to
   restart VS Code and run `/bic-playbook` again, then stop.
3. Ask the user to confirm they can open the DEV workspace URL and the IRIS URL from
   the Access table in their browser. If they can't, stop and tell them to request
   access from the project owner.

## Phase 2: One-time setup (RUNBOOK section 3)

1. From the repository root, run the setup commands exactly as written. Skip a step
   whose result already exists (`.venv\Scripts\python.exe`, `node_modules\`), but
   still run `npx playwright install chromium`.
2. Run every verification command and show the output. `render_check.py` must end
   with `errors=0`.
3. If a command fails, find the matching row in RUNBOOK section 12 and apply that
   fix. If no row matches, show the error and ask the user. Never delete anything
   outside `.venv\` and `node_modules\`.

## Phase 3: Start the app (RUNBOOK section 4)

1. Start `.venv\Scripts\streamlit.exe run streamlit_app.py` in a background terminal.
2. Confirm it answers with
   `(Invoke-WebRequest http://localhost:8501 -UseBasicParsing).StatusCode` (expect `200`).
3. Tell the user to open <http://localhost:8501>.

## Phase 4: Sign in (RUNBOOK section 5) — needs the user

1. Explain that there are two separate credentials: a Databricks token for Locust and
   a saved browser session for Playwright.
2. Walk the user through 5.1 (**Start browser sign-in**, then **Get token**). Wait
   until they confirm the **Authenticated** badge. No PAT is needed. If **Get token**
   fails, use RUNBOOK section 12 and ask about an existing `~/.databrickscfg`
   profile, but never open that file.
3. Walk the user through 5.2 (**Capture browser session**). Wait until they confirm
   **Looks usable**.

## Phase 5: Smoke checks (RUNBOOK section 6) — the user presses Start run

1. Guide the user through checks 1 and 2 in the app, one at a time, and ask for the
   result shown on **Results**.
2. Offer check 3. If the user wants it, ask for their Databricks login email and tell
   them to enter it as `BIC_TEST_USER_ID` in **Scenario environment**.
3. For any failure, explain the cause from RUNBOOK section 8 (status codes) and
   section 12, and suggest the fix.

## Finish

Summarise what is set up and what passed. Point to RUNBOOK section 7 for session and
load tests, and remind the user of the safety rules in section 11. Do not start any
run with more than 1 user unless the user explicitly asks.

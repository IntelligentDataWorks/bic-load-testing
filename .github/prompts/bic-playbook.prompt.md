---
agent: 'agent'
description: 'Set up this repository on Windows or macOS, start the BIC load-testing control centre, and guide sign-in and the first smoke checks'
---

You are setting up this repository for a new teammate. Read
`.github/copilot-instructions.md` first and follow its rules throughout.

## Phase 0: Ask two questions first

Ask both in one message, before running anything:

1. **"Are you on Windows or macOS?"**
   - Windows: the runbook is `docs/RUNBOOK.md`. Use PowerShell.
   - macOS: the runbook is `docs/RUNBOOK-mac.md`. Use zsh.
2. **"Do you need React UI tests (Playwright, a real browser)?"** Explain the choice
   in one line: **No** is enough for FastAPI BFF and Serving endpoint tests, and skips
   Node.js, `npm ci` and the Chromium download.

Then read the chosen runbook. From here on, "the runbook" means that file only. Run
only the commands it gives, exactly as written. Never use a command from the other
runbook, and never mix PowerShell and zsh syntax.

Work through the phases below in order. After each phase, tell the user in one or two
lines what passed and what comes next. Ask the user only the questions listed in the
runbook's section 10.2, and only when a step needs the answer.

## Phase 1: Prerequisites (runbook section 1)

The runbook's section 1 lists the **known-good version** of every tool. Keep the
user's setup on those versions.

1. Run every **Check** command from the Software table. If the user said **No** to UI
   tests, skip the Node.js row. Compare each version found with the **Known-good
   version** column.
2. **Same version:** leave it as it is. Git, Homebrew and Git Credential Manager: any
   version is fine.
3. **Missing:** ask before installing, then use the install command for that tool
   from the runbook. It installs the known-good version.
4. **Different version** (uv, Databricks CLI, Node.js): tell the user the version
   found and the known-good version, and that the tool is shared with their other
   projects. Ask whether to replace it with the known-good version (follow
   **Already installed?** in the runbook) or keep theirs. Change nothing without a yes.
5. Never upgrade npm on its own, even if npm suggests it. It comes with Node.js.
6. After any install, tell the user to open a new terminal (restart VS Code) and run
   `/bic-playbook` again, then stop.
7. Ask the user to confirm they can open the DEV workspace URL and the IRIS URL from
   the Access table in their browser. If they can't, stop and tell them to request
   access from the project owner.

## Phase 2: One-time setup (runbook section 3)

Section 3 installs Python, the Python packages, Playwright and Chromium at exact
versions. Use its commands exactly; never use `npm install`, `npm update`, or
`uv pip install` with anything other than `requirements.lock.txt`.

1. Run section 3.1. Skip it if `.venv` exists and section 3.3 already shows Python
   3.12.13, Locust 2.46.6 and Streamlit 1.64.0. If Python itself differs, delete
   `.venv` and run section 3.1 again.
2. Run section 3.2 **only if the user needs UI tests**. Skip `npm ci` if
   `npx playwright --version` already prints `Version 1.63.0`, but still run
   `npx playwright install chromium`.
3. Run the verification commands in section 3.3, show the output, and compare each
   line with the known-good version in its comment. Skip the `npx playwright
   --version` line if the user doesn't need UI tests. `render_check.py` must end with
   `errors=0`.
4. If a command fails, find the matching row in the runbook's section 12 and apply
   that fix. If no row matches, show the error and ask the user. Never delete anything
   outside `.venv` and `node_modules`.

## Phase 3: Start the app (runbook section 4)

1. Start the app with the start command from section 4, in a background terminal.
2. Confirm it answers with the check command from section 4 (expect `200`).
3. Tell the user to open <http://localhost:8501>.

## Phase 4: Sign in (runbook section 5) — needs the user

1. Explain the Databricks token (section 5.1). If the user needs UI tests, also
   explain that the browser session (section 5.2) is a second, separate credential.
2. Walk the user through 5.1 (**Start browser sign-in**, then **Get token**). Wait
   until they confirm the **Authenticated** badge. No PAT is needed. If **Get token**
   fails, use the runbook's section 12 and ask about an existing `~/.databrickscfg`
   profile, but never open that file.
3. Only if the user needs UI tests: walk them through 5.2 (**Capture browser
   session**). Wait until they confirm **Looks usable**.

## Phase 5: Smoke checks (runbook section 6) — the user presses Start run

1. Guide the user through check 1, and check 2 only if they need UI tests, one at a
   time. Ask for the result shown on **Results**.
2. Offer check 3. If the user wants it, ask for their Databricks login email and tell
   them to enter it as `BIC_TEST_USER_ID` in **Scenario environment**.
3. For any failure, explain the cause from the runbook's section 8 (status codes) and
   section 12, and suggest the fix.

## Finish

Summarise what is set up and what passed. Point to the runbook's section 7 for session
and load tests, and remind the user of the safety rules in section 11. If the user
skipped UI tests, say they can add them later with section 3.2. Do not start any run
with more than 1 user unless the user explicitly asks.

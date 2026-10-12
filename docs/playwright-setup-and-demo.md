# Playwright Setup & Demo Guide -- IRIS / BIC

Step-by-step reference for setting up, recording, and running the Playwright UI
tests against the deployed IRIS (DS Insights Companion) app, and for demoing
them live. Every command below is annotated with what it does, when to run it,
what success looks like, and whether it's a one-time or repeatable action.

> **Setting up an existing copy of this repository?** Playwright is already
> initialised here. Skip section 1 (`npm init playwright@latest` would overwrite
> the config and tests) and follow [RUNBOOK.md section 3](RUNBOOK.md#3-one-time-setup)
> instead: `npm install` then `npx playwright install chromium`. Sections 1 and 4
> record how the project was first built; sections 2, 3 and 5 onwards still apply.

Related files: [playwright.config.ts](../playwright.config.ts),
[tests/bic-smoke.spec.ts](../tests/bic-smoke.spec.ts),
[tests/bic-chat-complete.spec.ts](../tests/bic-chat-complete.spec.ts),
[.gitignore](../.gitignore).

---

## 1. One-time setup

### Verify prerequisites

```powershell
node --version
```
- **What it does:** Prints the installed Node.js version.
- **When to run:** Once, before initializing Playwright, and again only if you suspect your toolchain changed.
- **Success looks like:** A version string, e.g. `v24.17.0` (the tested version).
- **One-time or repeatable:** One-time check (safe to re-run anytime).

```powershell
npm --version
```
- **What it does:** Prints the installed npm version.
- **When to run:** Same time as the Node check, before `npm init playwright@latest`.
- **Success looks like:** A version string, e.g. `11.13.0`.
- **One-time or repeatable:** One-time check (safe to re-run anytime).

### Initialize Playwright

Run from `C:\Projects\bic-load-testing`:

```powershell
npm init playwright@latest
```
- **What it does:** Scaffolds the Playwright project -- `package.json`, `playwright.config.ts`, an example test, dependencies, and downloads browser binaries.
- **When to run:** Once per repository, the first time Playwright is added.
- **Selections used:** TypeScript, default `tests` directory, no GitHub Actions workflow, install Playwright browsers.
- **Success looks like:** The command completes with `playwright.config.ts`, `tests/example.spec.ts`, `package.json`, and `node_modules/` present in the folder.
- **One-time or repeatable:** One-time. Re-running it against an already-initialized project will prompt to overwrite existing config/tests -- don't re-run casually.

### Verify the installation

```powershell
npx playwright test
```
- **What it does:** Runs whatever test files currently exist (initially the generated example test) to confirm Playwright can launch a browser and execute a test.
- **When to run:** Immediately after `npm init playwright@latest`, before writing or recording any real tests.
- **Success looks like:** `X passed` with `0 failed`.
- **Note:** The generated example test navigates to `playwright.dev`, which may be blocked by the corporate network. A failure here on the `playwright.dev` example does **not** mean the Playwright installation is broken, and does **not** indicate anything about IRIS/Databricks access -- it only means that specific external site was unreachable.
- **One-time or repeatable:** One-time (as a install-verification step); safe to repeat any time you want a fast "is Playwright working at all" sanity check.

### Create the protected authentication directory

```powershell
New-Item -ItemType Directory -Force playwright\.auth
```
- **What it does:** Creates `playwright/.auth/`, the local folder where authenticated browser session state (cookies, storage) will be saved.
- **When to run:** Once, before the first `codegen --save-storage` capture.
- **Success looks like:** No error; the directory now exists (re-running with `-Force` is harmless and just confirms it's there).
- **Security note:** `playwright/.auth/`, `playwright-report/`, and `test-results/` must all be excluded via `.gitignore` -- the auth file contains live session credentials and must never be committed. This repo's [.gitignore](../.gitignore) already covers all three.
- **One-time or repeatable:** One-time (idempotent due to `-Force`, so harmless to re-run).

---

## 2. Authentication setup

### Capture the authenticated Databricks session

```powershell
npx playwright codegen --save-storage=playwright/.auth/bic-user.json "https://ds-insights-companion-ui-809065969263152.aws.databricksapps.com"
```
- **What it does:** Opens a real Playwright-controlled browser at the IRIS URL, lets you complete the Databricks SSO login by hand, and once you close it, writes the resulting cookies/storage to `playwright/.auth/bic-user.json`.
- **When to run:** The first time you set up auth, and again any time the saved session expires.
- **Procedure:** Let the Databricks login flow complete, wait for IRIS to load, then close both the browser window and the Inspector window so Playwright flushes the storage file.
- **Success looks like:** The browser and Inspector close cleanly with no error in the terminal, and `playwright/.auth/bic-user.json` now exists.
- **One-time or repeatable:** Repeatable -- re-run whenever the session expires (see Troubleshooting).

### Verify the authentication-state file

```powershell
Test-Path playwright\.auth\bic-user.json
```
- **What it does:** Confirms the authentication-state file was actually written.
- **When to run:** Immediately after every `codegen --save-storage` capture, and as the first step of any demo.
- **Success looks like:** `True`.
- **Security note:** Do not print or inspect the contents of this file -- it holds live session data.
- **One-time or repeatable:** Repeatable -- cheap, safe to run anytime as a pre-flight check.

---

## 3. Smoke testing

```powershell
npx playwright test tests/bic-smoke.spec.ts --project=chromium --headed
```
- **What it does:** Runs the smoke spec in a visible Chromium window. It verifies:
  - Databricks authentication is working (reused from `playwright/.auth/bic-user.json`).
  - The browser reaches IRIS without being redirected to an SSO/login page.
  - The deployed application actually loads (`response.ok()`).
  - Stable, user-visible elements are present: the `WELCOME TO IRIS` heading, the `NEW SESSION` button, the `VIEW DATA SOURCES` button, and the question input.
- **When to run:** Right after authentication is captured/verified, and as the first functional check in any demo or before recording a new journey.
- **Success looks like:** `1 passed`, `0 failed`.
- **One-time or repeatable:** Repeatable -- run this every time you need a fast confirmation that auth + the app shell are healthy.

---

## 4. Chat journey recording

### Open Codegen using the saved authenticated session (inspect only)

```powershell
npx playwright codegen --load-storage=playwright/.auth/bic-user.json "https://ds-insights-companion-ui-809065969263152.aws.databricksapps.com"
```
- **What it does:** Opens IRIS in a browser that's already authenticated (via the saved storage state), and shows generated locators/actions live in the Playwright Inspector as you interact with the page.
- **When to run:** When you want to explore selectors or experiment with a flow before committing to a recording.
- **Success looks like:** The Inspector displays generated Playwright actions as you click/type in the browser.
- **Important:** This mode does **not** save anything to a test file by itself -- it's for inspection only.
- **One-time or repeatable:** Repeatable, exploratory -- run as often as needed while designing a new test.

### Record and save a chat journey

```powershell
npx playwright codegen --target=playwright-test --load-storage="C:\Projects\bic-load-testing\playwright\.auth\bic-user.json" --output="C:\Projects\bic-load-testing\tests\bic-chat-complete.spec.ts" "https://ds-insights-companion-ui-809065969263152.aws.databricksapps.com"
```
- **What it does:** Records a real IRIS chat journey and writes the generated Playwright Test code directly to `tests/bic-chat-complete.spec.ts`.
- **When to run:** Once, to produce the initial draft of the chat-journey test (or again if you want to re-record from scratch).
- **Recorded journey:**
  1. Open IRIS.
  2. Click `NEW SESSION`.
  3. Enter a question.
  4. Click `Send Message`.
  5. Wait for the assistant response.
  6. Add an assertion for the visible response.
  7. Stop recording and close both the browser and Inspector.
- **Success looks like:** The Inspector/browser close cleanly and `tests/bic-chat-complete.spec.ts` is created/overwritten with generated code.
- **Note:** The generated test is a starting point, not the final version. It was subsequently refined by hand to:
  - Use the configured `baseURL` instead of a hardcoded URL.
  - Use the globally configured authentication (`storageState` in `playwright.config.ts`) instead of a per-test `test.use()`.
  - Wait for `POST /api/chat/stream` specifically (the button actually calls the streaming route, not `/api/chat`).
  - Validate the streaming response succeeded.
  - Parse and validate the terminal SSE `result` event.
  - Validate the assistant response text is non-empty.
  - Confirm the URL updates to a generated `session=chat_...` value instead of hardcoding one.
  - Confirm both the user's question and the assistant's answer render in the UI.
  - Avoid fixed sleep statements and hardcoded session IDs.
- **One-time or repeatable:** One-time to produce the initial recording; treat re-recording as a deliberate, occasional action since it overwrites your refined test.

### Confirm that the generated test file exists

```powershell
Test-Path .\tests\bic-chat-complete.spec.ts
```
- **What it does:** Confirms Codegen actually wrote the output file.
- **When to run:** Immediately after recording.
- **Success looks like:** `True`.
- **One-time or repeatable:** Repeatable -- cheap sanity check, safe to run anytime.

---

## 5. Test execution

### Run the complete chat journey visibly

```powershell
npx playwright test tests/bic-chat-complete.spec.ts --project=chromium --headed
```
- **What it does:** Replays the full chat journey in a visible Chromium browser -- useful for live demos and visual inspection.
- **When to run:** Whenever you want to watch the flow execute, e.g., during a demo or while debugging a failure.
- **Success looks like:** `1 passed`, `0 failed`. A successful run validates: Databricks authentication, React app loading, new-session creation, question submission, `/api/chat/stream` integration, the terminal SSE result event, a non-empty response, session-URL creation, and that both the user and assistant messages render in the UI.
- **One-time or repeatable:** Repeatable -- this is a normal, every-demo command.

### Run the complete chat journey headlessly

```powershell
npx playwright test tests/bic-chat-complete.spec.ts --project=chromium
```
- **What it does:** Runs the same journey without opening a visible browser window.
- **When to run:** For routine/automated validation where you don't need to watch it, e.g., CI or a quick local check.
- **Success looks like:** `1 passed`, `0 failed`.
- **One-time or repeatable:** Repeatable -- the standard day-to-day command.

---

## 6. Repeatability testing

```powershell
npx playwright test tests/bic-chat-complete.spec.ts --project=chromium --repeat-each=3 --workers=1
```
- **What it does:** Runs the same chat journey three times in a row to surface flaky selectors, authentication issues, or timing problems.
- **When to run:** Before a demo, or after changing a locator/assertion, to confirm the test is stable and not just passing by luck.
- **Flag reference:**
  - `--repeat-each=3` -- executes the test 3 times total.
  - `--workers=1` -- keeps the runs sequential so they don't interfere with each other (e.g., session state, rate limits).
  - `--project=chromium` -- uses only the configured Chromium project.
- **Success looks like:** `3 passed`, `0 failed`.
- **One-time or repeatable:** Repeatable -- run this as a stability gate whenever the test changes or before an important demo.

---

## 7. Running Playwright while Locust load is active

```powershell
npx playwright test tests/bic-chat-complete.spec.ts --project=chromium --workers=1
```
- **What it does:** Runs one real, complete browser journey against IRIS.
- **When to run:** From a **second terminal**, while a Locust run (e.g. `config/locust.deployed-stress.conf`) is actively generating API load in a first terminal.
- **Why this matters:**
  - Locust generates concurrent API traffic against the FastAPI BFF.
  - Playwright performs one real browser journey through the actual React UI at the same time.
  - Both tools run locally but target the same deployed Databricks App.
  - Together they confirm whether the React UI remains usable -- not just whether the API returns 200s -- while the BFF is under load.
- **Success looks like:** `1 passed`, `0 failed`, even while Locust's stats show active request volume.
- **One-time or repeatable:** Repeatable -- run during/after every load test where UI responsiveness under load needs to be demonstrated, not just API throughput.

---

## 8. Troubleshooting

- **`playwright.dev` example test fails during install verification:** The corporate network may block `playwright.dev`. This does not indicate a broken Playwright installation or any problem with IRIS/Databricks access -- it's specific to that one external site.
- **Chat/smoke test suddenly fails with an auth/login redirect:** The saved session in `playwright/.auth/bic-user.json` has likely expired. Regenerate it:
  ```powershell
  npx playwright codegen --save-storage=playwright/.auth/bic-user.json "https://ds-insights-companion-ui-809065969263152.aws.databricksapps.com"
  ```
  Then re-verify with `Test-Path playwright\.auth\bic-user.json` and re-run the smoke test.
- **Never commit or print the auth file:** `playwright/.auth/bic-user.json` holds live session data. It's gitignored; do not `cat`/open it to "check" it beyond `Test-Path`.
- **Need to see what happened in a failed run:**
  ```powershell
  npx playwright show-report
  ```
  - **What it does:** Opens the most recent HTML report -- test status, steps, timings, error messages, screenshots (captured `only-on-failure`), and traces (captured `retain-on-failure`, viewable with `npx playwright show-trace <path>`).
  - **When to run:** Immediately after any run you need to debug or demonstrate results from.
  - **Success looks like:** A browser tab opens showing the report UI with pass/fail counts and per-test detail.
  - **One-time or repeatable:** Repeatable -- run after every test run you want to inspect.

---

## 9. Demo execution sequence

Recommended order for a live demo:

1. Verify the authentication file:
   ```powershell
   Test-Path playwright\.auth\bic-user.json
   ```
2. Run the basic smoke test visibly:
   ```powershell
   npx playwright test tests/bic-smoke.spec.ts --project=chromium --headed
   ```
3. Run the complete chat journey visibly:
   ```powershell
   npx playwright test tests/bic-chat-complete.spec.ts --project=chromium --headed
   ```
4. Open the report:
   ```powershell
   npx playwright show-report
   ```

If authentication has expired, regenerate it before starting the sequence above:
```powershell
npx playwright codegen --save-storage=playwright/.auth/bic-user.json "https://ds-insights-companion-ui-809065969263152.aws.databricksapps.com"
```

**Every-demo commands:** steps 1-4 above (all repeatable).
**Occasional/setup commands:** everything in sections 1, 2 (initial capture), and 4 (initial recording) -- run only when setting up fresh, re-authenticating, or deliberately re-recording a journey.

# Recording a new Playwright journey

How to record a new IRIS browser journey with Playwright Codegen and turn it into a
reliable spec. Playwright is already set up in this repository: install it with
section 3.2 of [RUNBOOK.md](RUNBOOK.md#32-playwright-and-chromium-ui-tests-only)
(Windows) or [RUNBOOK-mac.md](RUNBOOK-mac.md#32-playwright-and-chromium-ui-tests-only)
(macOS). The `npx` commands below work as written in PowerShell and in macOS Terminal.

> **Do not run `npm init playwright@latest`.** It overwrites `playwright.config.ts`
> and the existing tests.

To *run* existing specs, use the control centre ([RUNBOOK.md section 6](RUNBOOK.md#6-first-run-smoke-checks)
and [section 7](RUNBOOK.md#7-testing-user-sessions)) or the command line
([cli-reference.md section 4](cli-reference.md#4-stage-3---react-ui-with-playwright)).

---

## 1. Before you record

You need a valid saved browser session in `playwright/.auth/bic-user.json`. Capture it
in the app (**Authentication** → **Browser session**, see
[RUNBOOK.md section 5.2](RUNBOOK.md#52-browser-session-for-playwright-tests)) or from
PowerShell:

```powershell
npx playwright codegen --save-storage=playwright/.auth/bic-user.json "https://ds-insights-companion-ui-809065969263152.aws.databricksapps.com"
```

Sign in, wait for **WELCOME TO IRIS**, then close **both** the browser and the
Inspector. The file holds live session cookies: never open, print or commit it.

## 2. Explore selectors (saves nothing)

```powershell
npx playwright codegen --load-storage=playwright/.auth/bic-user.json "https://ds-insights-companion-ui-809065969263152.aws.databricksapps.com"
```

The browser opens already signed in, and the Inspector shows the locators and actions
it generates as you click. Use this to try a flow before recording it.

## 3. Record to a new spec file

Always write to a **new** file, so you never overwrite a refined spec such as
`tests/bic-chat-complete.spec.ts`:

```powershell
npx playwright codegen --target=playwright-test --load-storage=playwright/.auth/bic-user.json --output=tests/<name>.spec.ts "https://ds-insights-companion-ui-809065969263152.aws.databricksapps.com"
```

Click through the journey, add an assertion for the visible result with the
Inspector's assert tools, then close the browser and the Inspector. Check the file
exists with `Test-Path tests\<name>.spec.ts` (macOS: `ls tests/<name>.spec.ts`).

## 4. Refine the recording

A raw recording is a draft, not a test. `tests/bic-chat-recorded.spec.ts` is kept as
an example of one: it has no assertions, a hard-coded session URL and an absolute
storage path, so it is never run. Before committing a new spec:

* Remove the `test.use({ storageState: ... })` block. The global `storageState` in
  [playwright.config.ts](../playwright.config.ts) applies, so the control centre can
  retarget it.
* Replace the full URL with `page.goto('/')`, so the configured `baseURL` applies.
* Remove hard-coded session IDs (`?session=chat_...`). Assert the URL pattern instead.
* Wait for the network call that matters, not a fixed sleep. The chat button calls
  `POST /api/chat/stream`, not `/api/chat`.
* Assert on what the user sees: the question and a non-empty answer on the page.
* Give the test a descriptive title; the control centre lists specs by title.

[tests/bic-chat-complete.spec.ts](../tests/bic-chat-complete.spec.ts) is the reference
example of all of these.

## 5. Try it

Run the new spec once, visibly, then three times in a row to catch flakiness:

```powershell
npx playwright test tests/<name>.spec.ts --project=chromium --headed
npx playwright test tests/<name>.spec.ts --project=chromium --repeat-each=3 --workers=1
```

Expect `1 passed`, then `3 passed`. In the control centre, press **Rescan repository**
on the Dashboard and the new spec appears under **React UI**.

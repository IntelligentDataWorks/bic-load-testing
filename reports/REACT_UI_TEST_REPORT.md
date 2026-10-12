# BIC/IRIS: React UI Test Report

| | |
|---|---|
| **Test date** | 2026-09-24, 08:04:58 to 08:46:52 UTC |
| **Environment** | Dev only: App `ds-insights-companion-ui` (`https://ds-insights-companion-ui-809065969263152.aws.databricksapps.com`), workspace `adidas-dwhm-lh-wrk-gazelle-dev` |
| **Tool** | Playwright 1.63.0 (Chromium, headless), Node v24.17.0 |
| **Specs** | [`tests/bic-smoke.spec.ts`](../tests/bic-smoke.spec.ts), [`tests/bic-chat-complete.spec.ts`](../tests/bic-chat-complete.spec.ts) |
| **Source** | This is extracted from [`FINAL_LOAD_STRESS_TEST_REPORT.md`](FINAL_LOAD_STRESS_TEST_REPORT.md), sections 2 to 5, 8, 9, 12 and 14 to 16, which remains the complete record |
| **Evidence** | `results/final-assessment/20260924-131117/stages/C1-*` to `C5b-*` and `R1c-*` (gitignored; local only) |

Every value was measured on the test date. Anything inferred is labelled as such.

---

## 1. Outcome

**The React UI passed every test: 9 of 9.** That is 1 landing-page smoke test and 8
complete chat journeys, with 0 failures, 0 flaky tests and 0 skipped tests.

* **Quiet system.** A user can open IRIS, start a new session, ask a business question
  and see the complete answer on screen. The first streamed text arrives after about 3.4
  to 4.6 s, and the complete answer after 30.9 to 43.1 s.
* **Two browsers at once.** Both passed. The complete answer took 30.9 s and 40.8 s.
* **During 5-user back-end load.** The journey still passed, but **the user waited
  30.2 s for the first streamed event** (normally about 4 s), and 59.4 s for the complete
  answer.
* **After load was removed.** The journey passed again, with the first event at 3.8 s and
  the complete answer at 38.2 s.
* **UI overhead is small.** The complete stream in the UI (30.9 to 43.1 s) is close to the
  direct serving-endpoint time for the same question (32.7 to 38.7 s). The Apps proxy, the
  BFF and streaming add only a few seconds.

**Not in scope:** concurrency above 2 browsers, and UI runs of more than a few minutes.
The approved-question BFF retest on 24 Sep did **not** re-run Playwright.

## 2. What the UI tests cover

| Path | Covers |
|---|---|
| **UI** | Chromium → Databricks Apps proxy → React → BFF `POST /api/chat/stream` → agent serving endpoint → Genie/SQL/LLM |
| **Combined** | 5 Locust BFF users (stage C5a) plus 1 Playwright chat journey running at the same time |

| Spec | What it checks |
|---|---|
| `bic-smoke.spec.ts` | The landing page loads for an authenticated user, and its heading, input box and buttons are visible |
| `bic-chat-complete.spec.ts` | Starts a new session and asks the KCC SS27 question ("How many articles do we have in Training KCC for SS27?"). Then checks three things: `POST /api/chat/stream` succeeded; a terminal `result` event arrived with non-empty answer text; and both the question and the start of the answer appear on the page. It does not check the exact wording, because the expected text comes from the API response. `test.setTimeout(120_000)` is set inside the test. |

Each chat journey makes **5 calls to the BFF**: `/api/me`, `/api/sessions` (twice),
`/api/chat/stream` and `/api/session-chat`. Apart from the stream itself, all returned 200
in 0.17 to 0.45 s.

## 3. Authentication

* **Browser session.** Playwright used the saved Databricks Apps session in
  `playwright/.auth/bic-user.json`, captured 2026-09-24 07:00 UTC. The offline check
  reported it valid until 2026-09-25 07:00 UTC, and the live smoke test confirmed it. Its
  contents were never printed or copied into the evidence.
* **Identity limitation.** Every browser run used **one real identity**. That identity
  holds `CAN_MANAGE` on the serving endpoint. The results do not show separation between
  users, or how users with restricted access see the UI.
* **Related 403-matrix findings** (see [`403_TEST_MATRIX.md`](403_TEST_MATRIX.md)):

| Row | Scenario | Result |
|---|---|---|
| M03 | A browser with no App session | **302** redirect to workspace sign-in (`/oidc/oauth2/v2.0/authorize`), not a 403 |
| M14 | A valid browser session | 9 of 9 UI tests passed |
| M15 | An expired browser session | **Historical** (2026-09-22 11:18 UTC): the test timed out waiting for `New Session`, and the failure screenshot shows the sign-in page, not a 403. Not reproduced live, because the session was valid. |

**Practical point:** an expired UI session looks like a login page or a timeout, not an
"access denied" error. Check and refresh the saved session before demos. Having the file
is not proof that it is valid.

## 4. Test configuration

| Stage | UTC | Spec and options | Workers | Runs | Question |
|---|---|---|---:|---|---|
| C1 landing smoke | 08:04:58 to 08:05:28 | `bic-smoke.spec.ts --workers=1` | 1 | 1 | n/a |
| C2 chat | 08:05:29 to 08:06:15 | `bic-chat-complete.spec.ts --workers=1` | 1 | 1 | KCC SS27 |
| C3 sequential | 08:06:33 to 08:08:46 | `bic-chat-complete.spec.ts --repeat-each=3 --workers=1 --trace on` | 1 | 3, one after another | KCC SS27 |
| C4 concurrent | 08:09:34 to 08:10:41 | `bic-chat-complete.spec.ts --repeat-each=2 --workers=2 --trace on` | 2 | 2 in parallel (started 15 ms apart) | KCC SS27 |
| C5b during load | 08:12:00 to 08:13:11 | `bic-chat-complete.spec.ts --workers=1 --trace on`, started 60 s into C5a (5 Locust BFF users, 08:11:01 to 08:15:15) | 1 | 1 | KCC SS27 |
| R1c recovery | 08:45:27 to 08:46:52 | `bic-chat-complete.spec.ts --workers=1 --trace on` | 1 | 1 | KCC SS27 |

Command pattern (from the repository root):

```text
PLAYWRIGHT_HTML_OUTPUT_DIR=<stage>/html-report PLAYWRIGHT_JSON_OUTPUT_NAME=<stage>/results.json PLAYWRIGHT_HTML_OPEN=never \
  npx playwright test tests/<spec> --project=chromium --workers=<1|2> [--repeat-each=N] [--trace on] \
  --output <stage>/artifacts --reporter "list,html,json"
```

All runs were headless, and `--trace on` was added to capture timings. Headed mode
affects only visibility, not behaviour.

## 5. Results

| Stage | Workers | Tests × repeats | Passed / failed / flaky / skipped | Test duration | Navigation (`page.goto`) | Stream first byte | Stream complete | Answer rendered |
|---|---:|---|---|---|---|---|---|---|
| C1 landing smoke | 1 | 1 × 1 | 1 / 0 / 0 / 0 | 8.3 s | not traced | n/a | n/a | Heading, input and buttons visible |
| C2 chat | 1 | 1 × 1 | 1 / 0 / 0 / 0 | 44.4 s | not traced | not traced | not traced | Yes |
| C3 sequential | 1 | 1 × 3 | 3 / 0 / 0 / 0 | 48.7, 38.7, 41.1 s | 3.3, 3.0, 5.4 s | 4.55, 4.55, 4.60 s | 43.1, 33.9, 33.9 s | Yes (3 of 3) |
| C4 concurrent | 2 | 1 × 2 (in parallel) | 2 / 0 / 0 / 0 | 64.2, 43.7 s | **21.3**, 7.3 s | 3.5, 3.4 s | 40.8, 30.9 s | Yes (2 of 2) |
| C5b during 5-user load | 1 | 1 × 1 | 1 / 0 / 0 / 0 | 67.1 s | 5.3 s | **30.2 s** | **59.4 s** | Yes |
| R1c recovery | 1 | 1 × 1 | 1 / 0 / 0 / 0 | 52.8 s | 11.1 s | 3.8 s | 38.2 s | Yes |
| **Total** | | **9 tests** | **9 / 0 / 0 / 0** | | | | | |

* **Page load.** Navigation took 3.0 to 21.3 s. The 21.3 s load happened while two
  browsers were loading at once. It is a single observation, not a trend.
* **Timings.** Stream first byte and completion come from the Playwright trace network
  timings for `POST /api/chat/stream`.
* **Traces.** No test failed, so there are no failure screenshots or failure traces. The
  traces kept from passing runs were **cleaned**: they keep action and network timings
  only, with no headers, cookies, request or response bodies, or page snapshots.

## 6. Combined result: UI during back-end load

**Setup:** while C5a ran 5 Locust users on the BFF (08:11:01 to 08:15:15 UTC), one browser
journey ran from 08:12:00 to 08:13:11 UTC.

* **It passed.** The answer streamed completely and appeared on the page, so the core
  user journey kept working under load.
* **The experience got noticeably worse:**

| Measure | Quiet system (C3, C4) | During 5-user load (C5b) | After load (R1c) |
|---|---|---|---|
| First streamed event | 3.4 to 4.6 s | **30.2 s** | 3.8 s |
| Complete answer | 30.9 to 43.1 s | **59.4 s** | 38.2 s |

* **What else was running.** During that window, 4 to 5 of the Locust users were waiting
  on full Genie/SQL answers of 75 to 86 s each. This overlap is consistent with queueing
  ahead of the agent serving endpoint, but it does not by itself prove the cause.
* **Bottleneck (confirmed later from serving traces; main report section 0.13).** At 10
  back-end users, requests waited a median of 55.6 s inside the serving endpoint before the
  agent started. The UI's 30 s first-event delay under 5-user load fits the same 4-request
  limit. Original text: All traffic goes to
  a single Small CPU served entity, which appears to process about 4 requests at a time.
  The UI and the BFF tier were not the constraint.
* **Extra load from the browser.** It added 5 BFF calls and 1 agent invocation on top of
  the Locust load.

## 7. Last stable and first degraded (UI view)

| | Result |
|---|---|
| **Stable** | 1 browser and 2 concurrent browsers on a quiet system: all passed, complete answer in 30.9 to 43.1 s |
| **Early warning** | 1 browser during 5 concurrent BFF users: passed, but 30.2 s before the first streamed event |
| **Not tested** | UI journeys during the 10-user stages, and more than 2 concurrent browsers |
| **Recovery** | Full (R1c) |

The approved-question BFF retest later confirmed the back-end limits: stable at 5
concurrent users, degraded at 10 (main report, section 0). No UI journey was run during
that retest.

## 8. Risks and limitations

1. **One identity** with high privileges. Per-user separation and restricted users are
   untested in the UI.
2. **One question.** Every chat journey asked the KCC SS27 question, so other domains and
   the product briefs were not exercised through the UI.
3. **Low UI concurrency.** At most 2 browsers. UI behaviour at 5 or more simultaneous
   browser users is unknown.
4. **Short runs.** No UI soak test was run. Browser-session expiry during use is covered
   only by the historical M15 evidence.
5. **The laptop is the client.** Every timing includes the network path from the
   corporate laptop.
6. **Wording not checked.** The chat test verifies that an answer is rendered, not that it
   is correct.

## 9. Recommendations

1. **Show that the request is queued or being worked on.** Users waited 30 s with no
   visible progress during load. Consider an early status event from the BFF, and a clear
   timeout message in the UI.
2. **Check the saved session before every demo or test run.** An expired session appears
   as a sign-in page or a timeout.
3. **Extend UI coverage:**
   * run a chat journey during a 10-user back-end stage;
   * ask one approved question from each accessible domain;
   * add a product-brief journey;
   * try 3 to 5 concurrent browsers.
4. **Add capacity to the agent serving endpoint.** This is the main report's
   recommendation. It is the most likely way to cut the waiting time users see under load.

## 10. Evidence

All paths are relative to
[`results/final-assessment/20260924-131117/`](../results/final-assessment/20260924-131117/).

| Evidence | Path |
|---|---|
| Playwright HTML reports | `stages/C*/html-report/`, `stages/R1c-ui-chat-recovery/html-report/`. Open with `npx playwright show-report <path>`. |
| Playwright JSON results | `stages/C*/results.json`, `stages/R1c-ui-chat-recovery/results.json` |
| Trace timings (extracted) | `stages/C3-*/`, `C4-*/`, `C5b-*/`, `R1c-*/trace-timings.json` |
| Cleaned traces | `stages/*/artifacts/**/trace.zip` (timings only) |
| Start and end times, console output | `stages/<stage>/started-utc.txt`, `ended-utc.txt`, `console.log` |
| Tools | `instrumentation/trace_timings.py`, `instrumentation/sanitize_traces.py` |
| Historical expired-session failure | `results/20260922-164849-react_ui-66e60a/` |

A secret scan of the evidence folder, including inside the zip archives, found no
tokens, cookie values or user email.

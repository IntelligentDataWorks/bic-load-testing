# 403 / Authentication Test Matrix: BIC/IRIS (dev)

**Test date:** 2026-09-24, 07:43 to 08:46 UTC. **Environment:** dev only.

**Targets:**
* Databricks App `ds-insights-companion-ui`
  (`https://ds-insights-companion-ui-809065969263152.aws.databricksapps.com`)
* Serving endpoint `ds-insights-companion-agent-dev` on workspace
  `adidas-dwhm-lh-wrk-gazelle-dev`

**Evidence:**
* [`D1-auth-matrix-probes/`](../results/final-assessment/20260924-131117/stages/D1-auth-matrix-probes/):
  `probes.json`, `config-facts-2.json`, `session-isolation-check.json`
* The load-stage summaries in
  [`final-summary.json`](../results/final-assessment/20260924-131117/final-summary.json)
* The issue tracker ([`inputs/403-issue-tracker.png`](../results/final-assessment/20260924-131117/inputs/403-issue-tracker.png))

## Scope and limits

* This is a **risk-based matrix of the authorization failure modes that were
  feasible and authorized**. It is **not** a test of every possible 403 error.
* We tested the deployed App **as it currently stands**, as instructed. We did not
  change or remove any scope, permission, credential or group, and we did not
  bypass any control.
* **One real identity was used throughout.** It is a Databricks OAuth U2M user
  that holds `CAN_MANAGE` on the serving endpoint. Tests that need a second
  identity, a least-privilege identity, or permission removal could not be run;
  they are marked *not authorized* or *skipped*.
* The tracker was supplied as an image. No `403 issue tracker.xlsx` exists in the
  repository, so the tracker rows below are transcribed from the image.
* **No HTTP 403 was observed in any request today.** That covers 618 Locust
  requests across 14 load stages, 14 single-request probes, about 15 read-only
  metadata and isolation requests, and 9 browser runs (1 smoke test and 8 chat
  journeys). All authentication failures we provoked returned **401**, a **302
  redirect to sign-in**, or **404**, and never 403.

## Identity and credential types (kept separate)

| Credential | How it was obtained | Observed facts (no secrets recorded) |
|---|---|---|
| Databricks API OAuth token (Locust, probes) | `databricks auth token --host <workspace>` (U2M), minted per stage | JWT scopes `all-apis offline_access`, **lifetime 3600 s**, audience = workspace `809065969263152` |
| Databricks Apps browser session (Playwright) | `playwright/.auth/bic-user.json`, captured 2026-09-24 07:00 UTC | App-host session cookie expiry 2026-09-25 07:00 UTC (offline check); validated live by the UI smoke test |
| OBO identity used by the App | The Apps proxy forwards the caller's identity to FastAPI | `/api/healthz` → `ok: true`, `auth_mode: "obo"`; `/api/me` → `authenticated: true`, `auth_mode: "obo"` |
| Test session / conversation ID | Created on the client (BFF: one `uuid4` per virtual user; serving: `final_assess_20260924_<uuid>` per request) or by the UI (New Session) | Not credentials. Many sessions under one identity do **not** prove isolation between users. |

## Response-source signatures (from live probes)

These signatures show which layer rejected a request. That helps with tracker item
**xx** ("various issues masked under 403 umbrella").

| Layer | Signature observed |
|---|---|
| **Databricks Apps proxy (API call)** | `401`, `application/json`, body exactly `{}` (2 bytes), about 0.7 s, `server: databricks` |
| **Databricks Apps proxy (browser)** | `302` → `adidas-dwhm-lh-wrk-gazelle-dev.cloud.databricks.com/oidc/oauth2/v2.0/authorize` |
| **FastAPI BFF** | JSON envelope `{error_code, message, request_id}`, for example `400 bad_request` |
| **Serving endpoint / workspace** | `401` with `WWW-Authenticate: Bearer realm="DatabricksRealm"` and `{error_code, message}`, where message is "Credential was not sent or was of an unsupported type for this API. [ReqId: …]"; `404 ENDPOINT_NOT_FOUND` for a wrong endpoint name |
| **App single-page-app fallback** | `200 text/html` (the React index page) for **unknown `/api/*` paths**: neither 404 nor 403 |

## Live and historical test cases

**Result key:**
* **Confirmed:** the hypothesis held.
* **Disproved:** the hypothesis was contradicted.
* **Inconclusive:** the evidence was not sufficient either way.
* **Skipped:** not feasible.
* **Not authorized:** it would require changes that were explicitly not permitted.

| ID | Hypothesis | Preconditions | Target | Identity | Safe procedure | Expected | Actual | Source | Evidence | Result | Guidance |
|---|---|---|---|---|---|---|---|---|---|---|---|
| M01 | An API call with no credential is rejected at the App front door, not by FastAPI | None | App `GET /api/healthz` | None | 1 request without an `Authorization` header | 401 or 302 from the proxy | **401**, body `{}` | Apps proxy | `probes.json` M01 | Confirmed | A `401 {}` means the request never reached FastAPI. Check the token first. |
| M02 | A malformed bearer token is rejected at the front door | None | App `GET /api/healthz` | Invalid string | 1 request with `Bearer not-a-real-token.malformed` | 401 | **401**, body `{}` | Apps proxy | M02 | Confirmed | Same as M01. It is not a 403. |
| M03 | A browser with no or expired App session is sent to sign-in, not shown a 403 | None | App `/` (HTML) | None | 1 request with `Accept: text/html` | 302 to OIDC | **302** → workspace `/oidc/oauth2/v2.0/authorize` | Apps proxy | M03 | Confirmed | An expired UI session looks like a login page or redirect. Refresh the browser session. |
| M04 | A valid OAuth U2M token is accepted and OBO is active | Token minted | App `GET /api/healthz` | U2M user | 1 request | 200, `ok: true` | **200**, `ok: true`, `auth_mode: obo` | FastAPI BFF | M04; A1 (7 of 7 × 200) | Confirmed | None |
| M05 | The BFF resolves the caller identity through OBO | Token | App `GET /api/me` | U2M user | 1 request (only the keys were recorded) | 200 | **200**, `authenticated: true`, `auth_mode: obo` | FastAPI BFF | M05 | Confirmed | None |
| M06 | A mistyped BFF path gives a 404, not a 403 | Token | App `GET /api/does-not-exist` | U2M user | 1 request | 404 | **200 `text/html`** (the single-page-app index) | App static/SPA fallback | M06 | **Disproved** (neither 404 nor 403) | Client code that expects JSON sees a parse error, not a 404. Recommend returning JSON 404 for unknown `/api/*` paths. |
| M07 | A session ID the caller does not own is refused without revealing data | Token | App `GET /api/session-chat?session_id=<random>` | U2M user | 1 request (random ID) | 403, 404, or empty | **200, `count: 0`, 0 chats** | FastAPI BFF | M07; `config-facts-2.json` | Confirmed (no leak, and no 403) | Unknown or foreign sessions return empty results, not 403. Cross-user ownership was **not** tested (needs a second identity). |
| M08 | FastAPI validation errors are distinguishable from authorization errors | Token | App `POST /api/chat` with an invalid body | U2M user | 1 request (rejected before any LLM call) | 400 or 422 | **400** `{error_code: bad_request, message, request_id}` | FastAPI BFF | M08 | Confirmed | Log and quote the `request_id` when triaging errors. |
| M09 | The serving endpoint rejects missing credentials with 401 | None | Serving `/invocations` | None | 1 request | 401 | **401**, "Credential was not sent or was of an unsupported type" | Serving / workspace auth | M09 | Confirmed | None |
| M10 | The serving endpoint rejects a malformed token with 401 | None | Serving `/invocations` | Invalid string | 1 request | 401 | **401** (same message) | Serving / workspace auth | M10 | Confirmed | None |
| M11 | A wrong serving endpoint name gives 404, not 403 | Token | `/serving-endpoints/final-assess-nonexistent-endpoint/invocations` | U2M user | 1 request | 404 | **404 `ENDPOINT_NOT_FOUND`** | Serving control plane | M11 | Confirmed | Check the endpoint name and path before treating a failure as a permission problem. |
| M12 | A valid token can invoke the serving endpoint directly | Token, `BIC_TEST_USER_ID` from SCIM `Me` | Serving `/invocations` | U2M user (`CAN_MANAGE`) | Stages B1 to B4, E3, R1a | 200 with a valid answer | **77 of 77 × 200**, all with non-empty output and no embedded error | Serving endpoint | `final-summary.json` | Confirmed | Only proves access for a `CAN_MANAGE` user |
| M13 | BFF-to-serving OBO authorization works end to end | Token | App `POST /api/chat`, `/api/chat/stream` | U2M user via OBO | Load stages A2 to A5, C5a, E1, R1b; UI journeys | 200 with a ChatResult | **73 of 73 chat turns returned HTTP 200.** 0 × 401, 403 or 5xx. 12 turns were app-level `action: error` domain refusals, not authorization errors. | BFF → serving → Genie/SQL | Stage `requests.jsonl`; `session-isolation-check.json` | Confirmed (for this identity) | Least-privilege users are untested (see M18). |
| M14 | A valid browser session gives authenticated UI access | Fresh storage state | App UI | Browser session | `bic-smoke.spec.ts` plus 8 chat journeys | Pass | **9 of 9 passed** | Apps proxy + React | C1 to C5b, R1c | Confirmed | Check the session before demos. Presence of the file is not proof it is valid. |
| M15 | An expired browser session causes a login redirect or timeout, not a 403 | Historical expired session | App UI | Expired browser session | Not reproduced live (the session was valid); historical run reviewed | Login page | **Historical, 2026-09-22 11:18 UTC:** test timed out waiting for `New Session`; the failure screenshot shows the sign-in page | Apps proxy | `results/20260922-164849-react_ui-66e60a/` | Confirmed (historical evidence) | Refresh with `npx playwright codegen --save-storage=…` |
| M16 | An expired or unaccepted API token is rejected at the front door | An already-expired token was **not** available | App | n/a | Not run live. Historical run reviewed | 401 | **Historical, 2026-09-21:** `results/report_*`, 212 of 212 requests got **401** in about 170 ms with a 2-byte body, which matches M01 and M02. The previous team context says a PAT was used; the credential type is not recorded in the file. | Apps proxy | `results/report_failures.csv` | Inconclusive for "expired". Consistent with a credential the proxy does not accept. | Use OAuth U2M for the App. Re-mint a token for each run; the lifetime is 3600 s. |
| M17 | A token from the wrong workspace is rejected | Needs an approved credential for another workspace | n/a | n/a | n/a | 401 | n/a | n/a | n/a | Skipped (no approved credential) | None |
| M18 | A user without access to a downstream resource gets a clear 403 | Needs an existing least-privilege test user or resource | n/a | n/a | n/a | 403 from BFF or downstream | n/a | n/a | n/a | Not authorized (no such identity; no permission changes allowed) | **Highest-value follow-up test** |
| M19 | Missing App `CAN USE` or endpoint `CAN QUERY` gives 403 | Needs a permission change or a user without them | n/a | n/a | n/a | 403 | n/a | n/a | Caller has `CAN_MANAGE` (M12 metadata) | Not authorized | None |
| M20 | Throttling returns 429 and is not confused with 403 | Load | App and serving | U2M user | Load stages up to 10 concurrent users | 429 if throttled | **0 × 429** in every stage. Endpoint `rate_limits` and AI Gateway rate limits are **null**. | n/a | `config-facts`, `final-summary.json` | Confirmed (no throttling at the tested load) | Saturation at 10 users showed up as **slower responses**, not as 429 or 403. |
| M21 | The App has the required user API scopes, including Genie | Read-only metadata | `GET /api/2.0/apps/ds-insights-companion-ui` | U2M user | 1 read-only request | Includes genie, serving, SQL | `user_api_scopes`: `serving.serving-endpoints`, `dashboards.genie`, `genie`, `sql.warehouses`, `sql.statement-execution`, `postgres`. Last deployment 2026-09-23 13:15 UTC. | Workspace Apps API | `config-facts-2.json` | Confirmed (current state) | Re-check the scopes after every deployment (tracker item 4). |
| M22 | No cross-session data mixing within one identity | Load stages completed | `/api/chat`, `/api/session-chat` | U2M user | Session echo checked on every chat turn; history read back for the 12 most recent sessions | 0 mismatches | **0 of 73** echo mismatches. **0** records from other sessions across 12 sessions. Stored turn counts matched the turns sent (13 of 13 for stage C5a). | FastAPI BFF | stage `requests.jsonl`; `session-isolation-check.json` | Confirmed (within one identity) | Isolation **between users** is untested. |

Probe `M13-permissions` in `probes.json`, `GET /api/2.0/permissions/serving-endpoints/<name>`,
returned `400 INVALID_PARAMETER_VALUE` because that API expects the endpoint ID,
not its name. This was a mistake in how the probe was written, not a finding. The
caller's permission level was read from the endpoint metadata instead
(`permission_level: CAN_MANAGE`).

## Tracker items compared with evidence

The tracker's own status column is the historical record. The "Today's evidence"
column contains only what was observed on 2026-09-24.

| # | Tracker issue | Tracker status | Today's evidence | Assessment |
|---|---|---|---|---|
| 1 | OBO token expires after 60 minutes | Resolved (token caching removed; a browser refresh clears the error) | The U2M access token lifetime is **3600 s** (JWT claims). No test ran longer than about 7 minutes on one token; tokens were minted fresh for every stage. | **Corroborated** (60-minute lifetime); expiry **not reproduced**. A 60-minute-plus soak test with one browser session is needed to confirm the fix. |
| 2 | Compute overload | Resolved (more memory and workers) | App compute is **MEDIUM** and ACTIVE. At 10 concurrent users, BFF health and profile calls stayed at a median of **0.25 to 0.3 s** with no 5xx. Degradation appeared on the chat path. | **Consistent with resolved for the App tier** at the tested load. The current constraint appears to be the serving endpoint (see the final report). |
| 3 | Access group not persisting on the Prod ML Serving backend | Ticket in IRIS to-do list | Production is out of scope; not tested. | **Not tested (production)** |
| 4 | App scope reset after deployment | Databricks investigating | Current dev scopes are complete, including genie (M21), after the 2026-09-23 deployment. No deployment was performed today. | **Inconclusive.** The current state is correct; whether scopes reset on deployment was not tested. |
| 5 | Genie scope not in App auth scope | "We will add genie to app auth scope" | `genie` and `dashboards.genie` are **present**. 33 full Genie/SQL answers succeeded through OBO. | **Confirmed fixed in the current dev state** |
| 6 | `OIDCTokenAuthenticatorInvalidScope` and `OAuthScopePolicyCheckScopesFailure` | Unknown ("?") | **Not observed** in any request. Reproducing it would need scope changes, which were not authorized. | **Inconclusive / not reproducible under current configuration** |
| 7 | Stale token generated by Databricks | Databricks platform issue; they will fix it | Not observed. No 401 or 403 appeared during any stage. | **Not observed** (cannot confirm the platform fix) |
| 8 | Error for only one or a few users | Databricks investigating | **Not testable** with one identity | **Not tested.** Needs several real test identities. |
| xx | Unclear logging; various issues show up as 403 | Feedback shared with Databricks | Today the proxy, BFF, serving and SPA-fallback responses had **distinct signatures** (see the table above). No 403 was produced by any tested failure mode. | Use the signature table to classify incidents. Ask for `request_id` or `ReqId` in every support ticket. |

## Conclusion

In the current dev deployment, every authentication failure mode we could safely
provoke was rejected correctly, and none of them surfaced as a 403:
* A missing, malformed or unaccepted credential got a **401** or a **redirect to
  sign-in**.
* Wrong paths got a **404**, or a **200 HTML** page for unknown App API paths.
* No **429** throttling occurred at the tested load.

For the one identity tested, OBO works end to end, the Genie scope is present, and
sessions stay isolated. The tracker items tied to **multiple or least-privileged
users** (6, 8, M18, M19) and to **deployment-time scope resets** (4) remain
**unverified**. They need a least-privilege test identity and a controlled
deployment test.

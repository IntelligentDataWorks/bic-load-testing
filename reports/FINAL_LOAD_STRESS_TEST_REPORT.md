# BIC/IRIS: Final Load, Stress and Reliability Test Report

| | |
|---|---|
| **Test date** | 2026-09-24, 07:43 to 08:47 UTC (13:13 to 14:17 IST) |
| **Environment** | Dev only: workspace `adidas-dwhm-lh-wrk-gazelle-dev`, App `ds-insights-companion-ui`, serving endpoint `ds-insights-companion-agent-dev` |
| **Runbook** | [`docs/cli-reference.md`](../docs/cli-reference.md) (formerly `docs/CLI_TESTING_DEMO_RUNBOOK.md`) |
| **Evidence folder** | [`results/final-assessment/20260924-131117/`](../results/final-assessment/20260924-131117/) (gitignored; local only) |
| **Companion reports** | [`LEADERSHIP_TEST_SUMMARY.md`](LEADERSHIP_TEST_SUMMARY.md), [`403_TEST_MATRIX.md`](403_TEST_MATRIX.md), [`BFF_APPROVED_QUESTION_VALIDATION.md`](BFF_APPROVED_QUESTION_VALIDATION.md) |
| **Highest approved load** | 10 concurrent virtual users for 5 minutes (BFF and serving endpoint, tested separately) |
| **BFF retest (section 0)** | 2026-09-24, 11:51 to 13:43 UTC. 43 approved questions screened, 31 completed. Load at 1, 5 and 10 users on the accessible domains. Evidence: [`results/bff-valid-question-retest/20260924-115127/`](../results/bff-valid-question-retest/20260924-115127/) |

All values in this report were measured on the test date. Anything that is
inferred, rather than measured, is labelled as such.

---

## 0. Revision: approved-question BFF retest (24 Sep 2026, 11:51 to 13:43 UTC)

This section **revises the BFF conclusions**. Sections 1 to 16 below are the **original
generic-question assessment**. They are unchanged so the two can be compared, and they
still hold for the serving endpoint, the UI and the 403 matrix, none of which were re-run.
The root-cause trace analysis is in section 0.13. The full retest detail, including all 43 questions, is in
[`BFF_APPROVED_QUESTION_VALIDATION.md`](BFF_APPROVED_QUESTION_VALIDATION.md). The evidence
is in
[`results/bff-valid-question-retest/20260924-115127/`](../results/bff-valid-question-retest/20260924-115127/).

### 0.1 Why the BFF retest was needed

* **Wrong questions.** The original BFF load used 5 generic sample questions. Of 73 chat
  turns, only 33 (45%) were full answers. 28 (38%) were clarifications and 12 (16%) were
  routing refusals.
* **Wrong verdict.** Locust counted every HTTP 200 as a success (gap G1).
* **Result.** The BFF capacity figure mixed fast non-answers with slow answers, so it did
  not represent business use.

### 0.2 Approved question catalogue

* **Source.** 43 approved questions:
  * 5 each for AI.Vision and ShareOfSearch;
  * 6 each for RangeInsights and FinanceInsights;
  * 5 for ProductReviews;
  * 4 for ProductBrief and 3 for ProductBriefFootball;
  * 8 for Chitchat and definitions;
  * 1 multi-domain question.
* **Verified.** All 43 match the routing examples in `orchestrator.dev.yaml` (commit
  `4da26de`) character for character.
* **Stored in** [`data/approved_questions.txt`](../data/approved_questions.txt), with IDs
  Q01 to Q43 and their domains.

### 0.3 Response-classification rules

Each chat turn gets exactly one outcome from
[`scenarios/chat_outcome.py`](../scenarios/chat_outcome.py). The outcome is based on the
BFF `ChatResult` contract (`action`, `insighter`, `text2sql`, `message`), not on HTTP status
or text length.

| Outcome | What it means | Counts as |
|---|---|---|
| `FULL_ANSWER` | `summarized` with a non-empty insight **and** SQL rows. For multi-domain questions, every requested subject must be addressed. | **Complete** |
| `VALID_DIRECT_RESPONSE` | `return_response` with content, for a brief, chitchat or definition | **Complete** |
| `CLARIFICATION` or `PARTIAL_ANSWER` | The system asks for more information, or answers only part of a multi-domain question | Incomplete, reported separately |
| `ROUTING_REFUSAL`, `APPLICATION_ERROR`, `EMPTY_RESPONSE`, `INCOMPLETE_STREAM`, `HTTP_ERROR`, `TIMEOUT` or `INVALID_CONTRACT` | Anything else | Failure |

* **Follow-up suggestions** are captured separately and never count as the answer. They
  were never mistaken for one (0 cases).
* **Tests.** 24 unit tests pass.
* **Manual review.** Four FinanceInsights turns had one record-count row and a "no data"
  answer. They were relabelled `EMPTY_RESPONSE` after a masked review.
* **Test code fixed.** Gap G1 is fixed in `basic_scenario.py`, and the new
  `approved_question_scenario.py` counts only completed outcomes as successes.
  Clarifications appear on their own Locust row.

### 0.4 Functional screening: completed answers against clarifications and failures

**Setup:** 43 questions, each asked once by one user, each in a new session.

| Outcome | Count | Questions |
|---|---:|---|
| `FULL_ANSWER` | 16 | AI.Vision 5, ShareOfSearch 5, RangeInsights 5, Multi-Domain 1 |
| `VALID_DIRECT_RESPONSE` | 15 | ProductBrief 4, ProductBriefFootball 3, Chitchat 8 |
| **Completed** | **31 of 43 (72.1%)** | |
| `CLARIFICATION` | 2 | Q15 (RangeInsights), Q17 (ProductReviews) |
| `APPLICATION_ERROR` (no data access) | 4 | Q18 to Q21: *"You don't have access to the 'ProductReviews' data source"*. This comes back as HTTP 200 with an in-band error, **not a 403**. |
| `EMPTY_RESPONSE` (no usable data) | 6 | Q22 to Q27 (FinanceInsights). The SQL ran and found zero records. Each took 94 to 159 s. |
| Routing refusals, partial answers, timeouts | 0 | |

**Laptop standby, not a system fault.** Five first attempts failed because the laptop
went into Windows Modern Standby. The Windows power events show this exactly, and the BFF
had stored 3 of those answers anyway. Each question was re-run once and was delivered.
The test tools now keep the machine awake.

### 0.5 Results by domain and exclusions

| Domain | Completed | Status in the load test |
|---|---:|---|
| AI.Vision | 5 / 5 | Included |
| ShareOfSearch | 5 / 5 | Included |
| RangeInsights | 5 / 6 | Included; Q15 excluded (clarification) |
| ProductBrief / ProductBriefFootball | 4 / 4 and 3 / 3 | Included |
| Chitchat and definitions | 8 / 8 | Included |
| Multi-Domain (Q43) | 1 / 1 | Tested separately, in the consistency run |
| **ProductReviews** | **0 / 5** | **Excluded: access-coverage limitation.** This user has no access to the data source. This is not a load-test failure. |
| **FinanceInsights** | **0 / 6** | **Excluded: data availability or permission requires investigation.** No usable data was returned. |

* **Two clarification questions were excluded.** Q15, and Q17, which is also a
  ProductReviews question.
* **The 12 excluded questions are not counted** as successes or in any capacity figure.
* **The original 80% gate was removed by the requester**, so these domains do not block
  testing of the accessible ones.

### 0.6 New 1-, 5- and 10-user results (accessible domains only)

**Workload:** a deterministic cycle over the 31 completed questions. It ran as 71.8%
analytical, 21.1% product brief and 7.0% chitchat (plan: 70/20/10).
* Every journey used a new test-owned session plus a history readback.
* Spawn rate 1 user per second. Graceful completion up to 330 s.
* Stop conditions were checked every 30 s. **No stage was stopped.**

| Stage | Users | Duration | Turns | Completed | Full-answer p50 / p90 / p95 / p99 | Full answers/min | Completed/min | Brief p50 | Chitchat p50 |
|---|---:|---:|---:|---:|---|---:|---:|---:|---:|
| P2-1 baseline | 1 | 3 min | 4 | 100% | 47.4 / 47.8 / 47.8 / 47.8 s (n 3) | 0.89 | 1.19 | 65.1 s | not run |
| P2-2 load | 5 | 5 min | 29 | 100% | **51.7 / 74.1 / 84.3 / 147.4 s** (n 21) | **3.51** | 4.85 | 64.2 s | 9.4 s |
| P2-3 stress | 10 | 5 min | 34 | 100% | **95.9 / 129.4 / 135.6 / 197.4 s** (n 24) | **3.66** | 5.18 | 112.7 s | 88.1 s |
| P2-4 recovery | 1 | 3 min | 4 | 100% | 43.9 / 48.6 / 48.6 / 48.6 s (n 3) | 0.92 | 1.22 | 61.1 s | not run |

* **Full answers are all analytical data answers** (AI.Vision, ShareOfSearch,
  RangeInsights). They are shown apart from direct responses, so fast chitchat does not
  hide data-answer latency.
* **One-user reference:** 18 analytical full answers from Phase 1 and P2-1. p50 41.7 s,
  p90 68.5 s. Its p95 of 172.5 s is one outlier, so stages are compared on p50 and p90.
* **Errors and isolation, all stages:**
  * 142 requests;
  * 0 HTTP failures, 0 timeouts, and 0 responses with status 401, 403, 429 or 5xx;
  * 0 session echo mismatches, and 71 of 71 history readbacks isolated.
* **Load generator:** CPU at most 38.8%.

### 0.7 Last stable level, based on full answers

**5 concurrent users.**
* 100% of turns completed.
* Full-answer p50 was 1.24 × the one-user reference, and p90 was 1.08 ×.
* Full-answer throughput rose from 0.89 to 3.51 per minute.
* Chitchat stayed at about 10 s, and briefs stayed at about 64 s.

### 0.8 First degraded level

**10 concurrent users.**
* Still 100% completed, with no errors.
* Full-answer p50 was **2.3 ×** the reference (95.9 s), and p90 was 1.89 ×.
* Throughput stayed **flat**: 3.66 against 3.51 full answers per minute.
* Fast replies queued behind data answers. Chitchat went from 9.4 s to 88.1 s, and briefs
  from 64 s to 113 s.
* **Queueing** (**confirmed in 0.13**). Little's law gives about 4 turns in service at once. This is consistent
  with the single Small serving entity found in §13. That is an inference, not a
  measurement.
* **Not stress to failure.** No failure point was reached, and 10 users was the approved
  ceiling.

### 0.9 Recovery

**Full.** P2-4 asked the same four questions as the baseline. Full-answer p50 was 43.9 s
(baseline 47.4 s), the brief took 61.1 s (baseline 65.1 s), and 100% completed.

### 0.10 Consistency

**Setup:** one user; Q02 (AI.Vision), Q06 (ShareOfSearch), Q12 (RangeInsights) and Q43
(Multi-Domain), 5 rounds each, in new sessions.

* **20 of 20 full answers. 100% consistent**, and no change of classification. Latency
  ranges were:
  * Q02: 47.7 to 51.0 s
  * Q06: 34.9 to 36.2 s
  * Q12: 32.4 to 39.2 s
  * Q43: 41.4 to 60.5 s
* **Q43 addressed both MBV and share of search every time.** The scope of its figures
  varied once (a Europe-wide instead of a German MBV), and the rank's magnitude differed
  once. This needs data-owner review.
* **Across 71 load turns and 20 repeats, no approved question was ever refused.** The
  original non-determinism ("sometimes answered, sometimes refused") was **not
  reproduced** with approved questions.

### 0.11 Comparison with the original generic-question test

| Measure | Original generic-question test | Approved-question retest | Change |
|---|---:|---:|---:|
| Questions/turns | 73 chat turns from 5 generic questions | 43 screened; 71 load turns and 20 repeats on the 31 usable ones | Different design |
| Completed answer rate | 45% `summarized` (33/73); 32.9% with data rows | Screening 72.1% (31/43); load **100% (71/71)** | Up |
| Clarification rate | 38% (28/73) | Screening 4.7%; load 0% | Down |
| Refusal/error rate | 16% (12/73) routing refusals | Screening 23.3% (access and no-data only, 0 routing refusals); load 0% | Different cause |
| 1-user full-answer p50/p95 | 84.5 / 86.1 s (n 2) | 47.4 / 47.8 s (n 3); reference 41.7 / 172.5 s (n 18) | Faster |
| 5-user full-answer p50/p95 | 71.4 / 81.8 s (A4, n 3) | 51.7 / 84.3 s (n 21) | Similar p95 |
| 10-user full-answer p50/p95 | 113.3 / 195.8 s (E1, n 17) | 95.9 / 135.6 s (n 24) | Lower |
| Full answers/minute (5 / 10 users) | 0.80 / 2.78 | 3.51 / 3.66 | Up (question mix) |
| Last stable load | 5 users | **5 users** | Unchanged |
| First degraded load | 10 users | **10 users** | Unchanged |

**Revised BFF conclusion.**
* **Capacity: unchanged, and now confirmed on real business questions.** Stable at 5
  concurrent users, degraded (latency about 2 ×, flat throughput, no errors) at 10.
* **Quality risk: changed.** The main risk is no longer routing inconsistency, which was
  not reproduced. It is now **domain coverage**. Two of the seven business domains
  returned nothing usable for this user.
* **Overall outcome: Ready with conditions**, for about 5 concurrent active users on the
  accessible domains only.
* **Root cause of the degradation (section 0.13): the serving endpoint's Small scale-out**
  (4 concurrent requests). The fix is Medium (8–16).

### 0.12 Remaining limitations

1. **Accessible domains only.** The capacity figures cover AI.Vision, ShareOfSearch,
   RangeInsights, the product briefs and chitchat. **No claim is made about
   ProductReviews or FinanceInsights scalability.**
2. **One identity.** Every concurrent session used one authenticated user, and that user
   holds `CAN_MANAGE`. The results show isolation across sessions, not across users.
3. **Small one-user samples.** The one-user stages had 3 full answers each. The one-user
   reference adds Phase 1 (18 samples) and the consistency run (15).
4. **Short runs, and not taken to failure.** At most 5 minutes per stage and 10 users.
5. **Content not verified.** Answer correctness was not checked against source data.
   Classification checks structure and subject coverage only. Q43's figure scope varied.
6. **Blocking endpoint only.** Only `POST /api/chat` was tested. The UI uses
   `/api/chat/stream`, and neither streaming nor Playwright was re-run.
7. **The laptop is the load generator.** Network latency is included, and standby is
   prevented only while the test scripts run.
8. **Test data left behind.** 137 new test-owned sessions (`lt-` prefix) remain
   under the test user. No cleanup method exists.

### 0.13 Bottleneck confirmed: serving traces and inference table (analysed 25 Sep)

This section replaces the *inferred* bottleneck in 0.8 and section 13 with measured
evidence.

**Sources (all read-only):**
* **MLflow serving traces** from `/Shared/ds-insights-companion/Orchestrator_Serving_Traces`
  (`MONITOR_EXPERIMENT_ID` on the endpoint). 100 traces from 13:06 to 13:42 UTC; 91 are
  the test's own requests, joined exactly on the `lt-` session IDs.
* **The endpoint's inference table**
  `lakehouse_dev.ds_insights_companion_lhdev.agent_payload`, for arrival time and
  execution time. It was queried on the user-approved warehouse `cadp-merch-execution-dev`
  with the user's dev profile.
* **The live metrics API**, for provisioned concurrency.

Only span names, timings and test session IDs were kept. No prompts, answers or user IDs
were kept. Evidence:
[`serving-traces/`](../results/bff-valid-question-retest/20260924-115127/serving-traces/SUMMARY.md)
and
[`serving-inference-table/`](../results/bff-valid-question-retest/20260924-115127/serving-inference-table/SUMMARY.md).

**Where each request's time went (median seconds):**

| Users | Endpoint total | **Wait before the agent started** | Agent run | LLM (all calls) | Single LLM call | Agent runs executing at once (max / average) |
|---:|---:|---:|---:|---:|---:|---|
| 1 | 45.6 | **0.0** | 45.5 | 17.9 | 3.1 | 1 / 0.95 |
| 5 | 55.3 | **3.8** | 46.7 | 18.0 | 3.0 | 5 / 3.91 |
| 10 | 96.5 | **55.6** | 43.6 | 17.7 | 3.0 | **5 / 4.23** |
| 1 (recovery) | 42.5 | **0.0** | 42.5 | 18.7 | 3.3 | 2 / 1.44 |

| Downstream work per request | 1 user | 10 users |
|---|---:|---:|
| Genie, including its SQL (ShareOfSearch) | 17.1 s | 17.7 s |
| Genie, including its SQL (RangeInsights) | 25.2 s | 20.6 s |
| AI.Vision sub-endpoint | 28.0 s | 28.2 s |
| In-process Python and CPU | about 0.1 s | about 0.1 s |
| Chitchat: wait / LLM | none asked | **78.4 s** / 8.6 s |

**Findings:**
1. **The BFF, the Apps proxy and the network were not the bottleneck.** Client time minus
   the endpoint's execution time was 0.2 to 1.8 s at every level.
2. **All of the extra latency at 10 users was waiting inside the serving container before
   the agent started.** The median wait went from 0 to 55.6 s, and 32 of 36 requests in
   the window waited more than 5 s. The agent's own run time did not grow.
3. **LLM, Genie (with its SQL) and the AI.Vision endpoint did not slow down** between 1
   and 10 users, so they were not the constraint at this load.
4. **CPU inside the container was not the constraint.** In-process time stayed at about
   0.1 s. A larger CPU or more memory per replica would not help.
5. **The served entity ran at most 4 to 5 agent runs at once** (average 4.23), even with
   10 requests inside the endpoint. The metrics API reports
   `provisioned_concurrent_requests_total = 4` for every served entity: this is the Small
   scale-out setting.

**Root cause: the serving endpoint's compute scale-out (Small, 4 concurrent requests).**

**Recommended fix:**
* Move the live entity (now `agent_91`) to **Medium (8–16 concurrent)**.
* Re-run the 10-user stage, then repeat the trace analysis. Expect the wait before the
  agent to fall to near 0, and 8 or more agent runs at once.
* Then watch LLM and Genie times. They have not yet been tested above about 5 concurrent
  requests.

**Also found: the model version changed during testing.** The served entity (model
version) changed at about 07:53, 08:06 and 13:31 UTC on 24 Sep.
* The original stages ran on three different versions: A2–A4; then A5 and B1–B4; then
  C5a, E1, E3, R1a and R1b.
* The original serving comparison between B4 (5 users) and E3 (10 users) therefore spans
  a version change.
* **All retest load stages (P2-1 to P2-4) ran on a single version**, and the consistency
  run switched version at 13:31.
* The endpoint was reconfigured again at 15:54 UTC, and 100% of traffic now goes to
  `agent_91`.

---

# Original generic-question assessment (sections 1 to 16)

The original findings are kept as they were. Retest additions are marked **[Retest]**.

## 1. Executive outcome

> **Superseded for the BFF by section 0.** The capacity levels below were confirmed by the
> approved-question retest. The answer-quality findings apply to the generic questions only.

**Overall: Ready with conditions for about 5 concurrent active chat users (the
tested level). Performance degraded at 10 concurrent users. This is not a
stress-to-failure result.**

* **Functional:** every tested path worked. Across all stages there were 0 HTTP
  failures, 0 timeouts, and 0 responses with status 401, 403, 429 or 5xx:
  * 618 Locust requests
  * 77 of 77 direct serving invocations, each returning a valid, non-empty answer
  * 8 of 8 complete browser chat journeys, plus the landing-page smoke test
* **Application-level quality:** **12 of 73 BFF chat turns (16 %)** returned HTTP
  200 with `action: "error"`. These were domain-routing refusals such as "I could
  not tell which data this question is about". A further **28 (38 %)** were
  clarifying questions. These outcomes depend on the question: the repository's
  generic sample questions often fall outside the supported data domains. The same
  question was **sometimes answered and sometimes refused**. The repository's
  Locust scenario counts these error turns as successes (runbook gap G1); this
  assessment counted them separately.
* **Last stable level: 5 concurrent users.** At that level:
  * Serving endpoint: median latency +16 % against the 1-user baseline, p95 1.6 ×.
  * BFF: fast replies (clarifying questions) were unchanged; full answers stayed
    near baseline.
  * Early warning: with 5 concurrent heavy questions, the UI waited **30 s for the
    first streamed event** (about 4.5 s when the system is otherwise quiet).
* **First degraded level: 10 concurrent users.**
  * Serving endpoint: median latency **2.2 ×** baseline, p95 **2.76 ×**, and
    throughput **flat** (6.3 answers per minute against 6.4 at 5 users).
  * BFF: full-answer p95 **2.1 ×** baseline. Clarifying replies went from about
    8 s to a median of **51.5 s**.
  * No errors at this level: the degradation shows only as waiting time.
* **Recovery:** complete. After load was removed:
  * Serving median 34.2 s (baseline 33.5 s)
  * BFF full answers 53 to 86 s (baseline 84 to 86 s)
  * UI journey passed, first streamed event after 3.8 s
* **Likely bottleneck (inferred; see section 13):** the agent serving endpoint
  sends **100 % of traffic to a single Small CPU served entity**. The measured
  throughput plateau works out to about 3.6 requests in service at once, which is
  consistent with a Small workload size. The BFF tier stayed responsive.
* **403:** no 403 occurred today. Every tested authentication failure returned
  401, a 302 redirect or a 404 with a distinguishable signature. Details are in
  [`403_TEST_MATRIX.md`](403_TEST_MATRIX.md).

## 2. Scope and architecture paths tested

| Path | Covers | Tool |
|---|---|---|
| **BFF** | Laptop → Databricks Apps proxy → FastAPI BFF (`/api/health`, `/api/healthz`, `/api/me`, `/api/data-sources`, `/api/sessions`, `/api/chat`, `/api/session-chat`, `/api/visualization`, `/api/chat/stream`) → agent serving endpoint (OBO) → Genie/SQL/LLM | Locust (`basic_scenario.py`, `stream_scenario.py`, `smoke_healthz.py`) |
| **Direct serving** | Laptop → Model Serving `ds-insights-companion-agent-dev/invocations` → agent → Genie/SQL/LLM. Bypasses the React UI, the Apps proxy and the BFF. | Locust (`serving_endpoint_smoke.py`, `serving_endpoint_load.py`) |
| **UI** | Chromium → Apps proxy → React → BFF `/api/chat/stream` → agent. The rendered answer is checked. | Playwright (`bic-smoke.spec.ts`, `bic-chat-complete.spec.ts`) |
| **Combined** | 5 Locust BFF users plus 1 Playwright chat journey at the same time | Both |
| **Authentication** | Front-door, BFF and serving auth failure modes; OBO; scopes | Single-request probes |

**Not covered:**
* Production
* Several real identities or least-privilege users
* `/api/schema`, `/api/table/sort`, `/api/query-feedback`, `/api/query-metrics`
  and `/api/historical-query`, which the repository's scenarios do not cover
* Loads above 10 users, and runs longer than about 7 minutes

## 3. Environment and test date

| Item | Value |
|---|---|
| Load generator | Windows 11 laptop, 8 logical CPUs, 32 GB RAM, running on the corporate network. Every latency figure includes the network path from the laptop to the workspace. |
| Tools | Python 3.12.13, Locust 2.46.6, Node v24.17.0, Playwright 1.63.0 (Chromium), Databricks CLI v1.4.0 |
| App | `ds-insights-companion-ui`, compute **MEDIUM**, state ACTIVE, last deployment 2026-09-23 13:15 UTC |
| Serving endpoint | `ds-insights-companion-agent-dev`: state READY. Six served entities, **all Small, CPU, scale-to-zero off**. **100 % of traffic goes to `…agent_89`**; the other five receive 0 %. No rate limits and no AI Gateway rate limits are configured. |
| Production check | Every host was compared with the `production_host_markers` list in `config/app-settings.json`; none matched. |

## 4. Authentication model and identity limitations

* **API (Locust and probes):** a Databricks **OAuth U2M** access token minted with
  `databricks auth token` for **each stage**. It was passed to Locust only through
  the child process environment and was never printed or saved. Token lifetime is
  **3600 s**, and its scopes are `all-apis offline_access`.
* **Browser (Playwright):** the saved Databricks Apps session
  `playwright/.auth/bic-user.json`, captured 2026-09-24 07:00 UTC. The offline
  check reported it valid until 2026-09-25 07:00 UTC, and the live UI smoke test
  confirmed it.
* **OBO:** the BFF reported `auth_mode: "obo"` and `authenticated: true`.
* **Serving identity:** `BIC_TEST_USER_ID` was resolved from the same token through
  SCIM `Me`, so the payload identity matches the token. It is redacted in all
  evidence.
* **Sessions:**
  * BFF: one client-created session ID per virtual user, reused for every turn.
  * Streaming: a new session is created by the backend for each turn.
  * Serving: a new `final_assess_20260924_<uuid>` session per request.
  * UI: a new session per journey.
* **Limitation:** **every virtual user and browser shared one real identity, and
  that identity holds `CAN_MANAGE` on the endpoint.** The results show concurrency
  across sessions under one user. They do **not** show isolation between users,
  per-user limits, or how least-privileged users behave.

## 5. Test configuration by stage

All stages used the repository's own configs and scenarios, **unchanged**. A
read-only audit add-on,
[`instrumentation/audit_plugin.py`](../results/final-assessment/20260924-131117/instrumentation/audit_plugin.py),
was loaded alongside each scenario. It:
* records the status code, latency and application verdict of every request;
* checks the session ID returned against the one sent;
* samples CPU and memory on the load generator;
* enforces the agreed stop conditions automatically.

It never changes Locust's pass or fail outcome.

**Deviations from the runbook:**
* Load stages ran for **3 minutes plus a grace period of up to 120 s**, so each
  stage stayed within the 5-minute approval rule. The runbook's 2-minute and
  5-minute stages were adjusted for this.
* The approved stages at 10 users ran for 5 minutes plus up to 180 or 190 s of
  grace.
* UI evidence runs were headless. `--trace on` was added to capture timings.

| Stage | Config (scenario) | Users | Spawn rate | Run time + grace | Question(s) |
|---|---|---:|---:|---|---|
| A1 | `locust.deployed-smoke.conf` (`smoke_healthz.py`) | 1 | 1/s | 10 s | n/a |
| A2 | `locust.deployed-stress.conf` (`basic_scenario.py`) | 1 | 1/s | 90 s + 180 s | `data/sample_questions.txt` (random) |
| A3 | same | 1 | 1/s | 3 min + 120 s | same |
| A4 | same | 5 | 1/s | 3 min + 120 s | same |
| A5 | `locust.deployed-stream.conf` (`stream_scenario.py`) | 1 | 1/s | 60 s + 120 s | "What were last week's top selling products?" |
| B1 | `locust.serving-smoke.conf` (`serving_endpoint_smoke.py`) | 1 | 1/s | 1 request (60 s + 190 s) | "Hello" |
| B2 | same | 1 | 1/s | 1 request | "How many articles do we have in Training KCC for SS27?" |
| B3 | `locust.serving-stress.conf` (`serving_endpoint_load.py`) | 1 | 1/s | 3 min + 120 s | KCC SS27 question |
| B4 | same | 5 | 1/s | 3 min + 120 s | KCC SS27 question |
| C1 to C4 | `bic-smoke.spec.ts`, `bic-chat-complete.spec.ts` | 1 or 2 workers | n/a | 1, 1, 3 sequential, 2×2 concurrent | KCC SS27 question (in the spec) |
| C5a + C5b | A4 config + 1 chat journey starting 60 s into the load | 5 + 1 | 1/s | 3 min + 120 s | as above |
| D1 | Authentication probes | 1 | n/a | 14 single requests | n/a |
| **E1** (approved) | `locust.deployed-stress.conf` | **10** | 1/s | 5 min + 180 s | sample questions |
| **E3** (approved) | `locust.serving-stress.conf` | **10** | 1/s | 5 min + 190 s | KCC SS27 question |
| R1a, R1b, R1c | Serving 1 user, BFF 1 user, 1 UI journey | 1 | 1/s | 3 min + 120 s each; 1 journey | as above |

**Automatic stop conditions** were checked every 30 s. The run would stop on any of:
* failure rate above 5 % in two consecutive windows
* three or more 401 or 403 responses in one window
* three or more 429 or 5xx responses in two consecutive windows
* p95 above 3 × the one-user baseline in two consecutive windows
* system CPU above 95 % in two consecutive windows

**No stage was stopped.**

The p95 check did not work during stages A1 to E3: Git Bash rewrote the endpoint
arguments into Windows paths, so they matched no requests. It was fixed for the
recovery stages. **Re-checking every stage afterwards from the raw request records
found no breach.** The highest 30-second-window p95 was 196 s for BFF chat,
against a limit of 258 s, and 108 s for serving, against a limit of 116 s. The
data is under `posthoc_p95_guard` in `final-summary.json`.

## 6. FastAPI BFF results

### 6.1 Per-stage measurements

The business-call latency is `POST /api/chat`, measured to the complete JSON
answer. Where there are fewer than about 20 samples, **p95 and p99 simply equal the
maximum** and should not be read as percentiles.

| Stage | Start to end (UTC) | Users (configured / peak) | Load window | Requests (OK / fail) | RPS | Fail/s | All-request avg, min, max | `/api/chat` n | chat p50 / p90 / p95 / p99 | chat avg size |
|---|---|---|---:|---|---:|---:|---|---:|---|---:|
| A1 health smoke | 07:43:37 to 07:43:47 | 1 / 1 | 9.1 s | 7 / 0 | 0.77 | 0 | 0.43 s, 0.32 s, 1.04 s | n/a | `/api/healthz` 0.34 / 1.04 / 1.04 / 1.04 s | 63 B |
| A2 single pass | 07:43:57 to 07:45:35 | 1 / 1 | 97.7 s | 6 / 0 | 0.061 | 0 | 14.4 s, 0.16 s, 84.5 s | 1 | 84.5 s (single sample) | 2019 B |
| A3 baseline | 07:46:21 to 07:49:25 | 1 / 1 | 184 s | 27 / 0 | 0.147 | 0 | 4.4 s, 0.17 s, 86.1 s | 4 | 8.1 / 86.1 / 86.1 / 86.1 s | 694 B |
| A4 load | 07:49:49 to 07:53:49 | 5 / 5 | 238.5 s | 195 / 0 | 0.818 | 0 | 2.5 s, 0.16 s, 81.8 s | 27 | 8.2 / 71.3 / 71.4 / 81.8 s | 672 B |
| C5a combined | 08:11:01 to 08:15:15 | 5 / 5 | 254 s | 89 / 0 | 0.350 | 0 | 9.2 s, 0.16 s, 138.3 s | 13 | 74.6 / 101.4 / 138.3 / 138.3 s | 1896 B |
| **E1 load** | 08:25:06 to 08:31:28 | **10 / 10** | 380.2 s | 192 / 0 | 0.505 | 0 | 14.2 s, 0.16 s, 195.8 s | 26 | **107.7 / 180.3 / 180.8 / 195.8 s** | 1966 B |
| R1b recovery | 08:42:24 to 08:45:26 | 1 / 1 | 180 s | 18 / 0 | 0.100 | 0 | 8.0 s, 0.17 s, 85.5 s | 2 | 52.9 / 85.5 / 85.5 / 85.5 s | 3117 B |

**Status codes:** every request in every BFF stage returned **200**. There were 0
timeouts and 0 responses with status 401, 403, 429 or 5xx.

The BFF has no client timeout (runbook gap G2), so any hang would have shown up as
a stage that never finished. None did.

### 6.2 Chat outcomes and latency by type of reply

`/api/chat` latency has two very different groups: clarifying or refusal replies
take a few seconds, and full Genie/SQL answers take more than a minute. The two are
reported separately.

| Stage | Users | Full answers (`summarized`): n, median, range | Clarifications: n, median, range | App-level `error`: n, median, range |
|---|---:|---|---|---|
| A2 | 1 | 1, 84.5 s | 0 | 0 |
| A3 | 1 | 1, 86.1 s | 2, 7.6 s (7.0 to 8.1) | 1, 10.0 s |
| A4 | 5 | 3, 71.4 s (71.3 to 81.8) | 18, 8.1 s (6.4 to 15.8) | 6, 9.3 s (8.0 to 10.8) |
| C5a | 5 | 9, 79.8 s (46.8 to 138.3) | 1, 6.6 s | 3, 11.8 s (9.4 to 16.6) |
| **E1** | **10** | 17, **113.3 s** (88.1 to 195.8) | 7, **51.5 s** (6.8 to 110.2) | 2, 45.5 s (44.5 to 46.5) |
| R1b | 1 | 2, 69.2 s (52.9 to 85.5) | 0 | 0 |
| **Total** | n/a | **33 (45 %)** | **28 (38 %)** | **12 (16 %)** |

* The `error` turns all returned HTTP 200 with domain-routing messages, for example
  "I could not tell which data this question is about. Please name a metric,
  product, market or time period…" and "This query does not fall within the
  supported data domains…". These are **functional failures from the user's point
  of view**, not errors in the platform.
* **Routing is non-deterministic.** "Compare year-over-year growth for our top 5
  categories" was refused 5 times in A4 and once in A3, but produced a full answer
  with 20 SQL rows once in A4, twice in C5a, and again in E1 and R1b.
* `/api/visualization` never ran. It runs only after a turn that returned SQL rows,
  and the scenario loop moved on or stopped before it.

### 6.3 Sessions, journeys and validation

| Stage | Sessions created | Sessions/s | Completed journeys (non-error, non-empty reply) | Journeys/min | Session echo mismatches |
|---|---:|---:|---:|---:|---:|
| A2 | 1 | 0.0102 | 1 | 0.61 | 0 |
| A3 | 1 | 0.0054 | 3 | 0.98 | 0 |
| A4 | 5 | 0.021 | 21 | 5.28 | 0 |
| C5a | 5 | 0.0197 | 10 | 2.36 | 0 |
| E1 | 10 | 0.0263 | 24 | 3.79 | 0 |
| R1b | 1 | 0.0056 | 2 | 0.67 | 0 |

* **What "sessions/s" means here.** `basic_scenario.py` creates **one session per
  virtual user** and reuses it for every turn. The session rate for the BFF
  therefore reflects how fast users started, not how many sessions the system can
  create per second. The count of sessions is proven by the unique `session_id`
  values the server returned.
* **Streaming (A5):** sessions are created by the backend and are not visible to
  Locust, so they are **not measured**. Adding the returned `session_id` to the
  stream scenario's result record would be enough to measure them.
* **Isolation:** every chat response returned the `session_id` it was sent (0 of 73
  mismatches). Reading back the history of the 12 most recent sessions found 0
  records belonging to another session. The number of stored turns matched the
  number sent: 13 of 13 in C5a.

### 6.4 Streaming (A5, 1 user, 7 turns)

| Measure | p50 | Max |
|---|---:|---:|
| Response headers (`POST /api/chat/stream`) | 4.2 s | 5.9 s |
| Time to first SSE event | 4.2 s | 5.9 s |
| Time to terminal `result` (complete) | 7.2 s | 8.9 s |

All 7 streams ended with a valid terminal `result` event, and no in-band `error`
events occurred. The fixed question in the scenario mostly gets a clarifying reply
on `/api/chat`, and these timings match that. The stream scenario does not expose
the reply type, so this is **not measured**.

## 7. Serving-endpoint results

| Stage | Start to end (UTC) | Users (configured / peak) | Load window | Invocations (valid / invalid) | RPS | p50 / p90 / p95 / p99 | Avg, min, max | Avg size | Sessions (unique) | Sessions/s | Answers/min |
|---|---|---|---:|---|---:|---|---|---:|---:|---:|---:|
| B1 "Hello" | 07:55:39 to 07:56:39 | 1 / 1 | 59 s | 1 / 0 | 0.017 | 9.9 s (1 sample) | n/a | 906 B | 1 | 0.017 | 1.0 |
| B2 KCC SS27 | 07:56:41 to 07:57:41 | 1 / 1 | 60 s | 1 / 0 | 0.017 | 34.6 s (1 sample) | n/a | 4159 B | 1 | 0.017 | 1.0 |
| B3 baseline | 07:57:53 to 08:00:53 | 1 / 1 | 180 s | 5 / 0 | 0.028 | 33.5 / 38.7 / 38.7 / 38.7 s | 34.5 s, 32.7 s, 38.7 s | 4253 B | 5 | 0.028 | 1.67 |
| B4 load | 08:01:07 to 08:04:42 | 5 / 5 | 214.3 s | 23 / 0 | 0.107 | 38.7 / 54.4 / 61.6 / 71.5 s | 41.1 s, 31.2 s, 71.5 s | 4332 B | 23 | 0.107 | 6.44 |
| **E3 load** | 08:31:53 to 08:38:34 | **10 / 10** | 398.6 s | 42 / 0 | 0.105 | **75.1 / 103.5 / 106.7 / 108.4 s** | 80.2 s, 32.4 s, 108.4 s | 4797 B | 42 | 0.105 | **6.32** |
| R1a recovery | 08:39:03 to 08:42:10 | 1 / 1 | 186 s | 5 / 0 | 0.027 | 34.2 / 40.0 / 40.0 / 40.0 s | 35.6 s, 31.9 s, 40.0 s | 4800 B | 5 | 0.027 | 1.61 |

* **Validation.** A response counted as valid only with HTTP 200, a non-empty
  `output`, no top-level `error`, and no `output` item of type `error`. The answer
  length was also checked (3,257 to 3,665 characters for the business question).
  **77 of 77 were valid, with 0 embedded errors.** There were 0 timeouts at the
  180 s client limit, and 0 responses with status 401, 403, 429 or 5xx.
* **Streaming** does not apply: the serving scenarios are not streamed.
* **Why serving sessions/s is meaningful here.** Each invocation creates a new
  session, so here the session rate equals the number of completed invocations
  per second.

## 8. React UI results

| Stage | Workers | Tests × repeats | Passed / failed / flaky / skipped | Test duration | Navigation (`page.goto`) | Stream first byte | Stream complete | Answer rendered |
|---|---:|---|---|---|---|---|---|---|
| C1 landing smoke | 1 | 1 × 1 | 1 / 0 / 0 / 0 | 8.3 s | not traced | n/a | n/a | Heading, input and buttons visible |
| C2 chat | 1 | 1 × 1 | 1 / 0 / 0 / 0 | 44.4 s | not traced | not traced | not traced | Yes |
| C3 sequential | 1 | 1 × 3 | 3 / 0 / 0 / 0 | 48.7, 38.7, 41.1 s | 3.3, 3.0, 5.4 s | 4.55, 4.55, 4.60 s | 43.1, 33.9, 33.9 s | Yes (3 of 3) |
| C4 concurrent | 2 | 1 × 2 (in parallel; started 15 ms apart) | 2 / 0 / 0 / 0 | 64.2, 43.7 s | **21.3**, 7.3 s | 3.5, 3.4 s | 40.8, 30.9 s | Yes (2 of 2) |
| C5b during 5-user load | 1 | 1 × 1 | 1 / 0 / 0 / 0 | 67.1 s | 5.3 s | **30.2 s** | **59.4 s** | Yes |
| R1c recovery | 1 | 1 × 1 | 1 / 0 / 0 / 0 | 52.8 s | 11.1 s | 3.8 s | 38.2 s | Yes |

* The chat test checks that `POST /api/chat/stream` succeeded, that a terminal
  `result` event arrived with non-empty answer text, and that both the question and
  the start of that answer appear on the page.
* Each journey makes **5 calls to the BFF**: `/api/me`, `/api/sessions` (twice),
  `/api/chat/stream` and `/api/session-chat`. All returned 200 and took 0.17 to
  0.45 s, apart from the stream itself.
* **Comparing the UI with the direct serving call for the same question:** the UI's
  complete stream took 30.9 to 43.1 s when the system was quiet. The direct serving
  baseline was 32.7 to 38.7 s. **The Apps proxy, BFF and streaming therefore add
  only a few seconds.**
* Page navigation varied from 3.0 to 21.3 s. The 21.3 s load happened while two
  browsers were loading at once. This is a single observation, not a trend.
* No failures occurred, so there are no failure screenshots or failure traces. The
  traces kept from the passing runs were **cleaned**: action timings and network
  timings only, with no headers, cookies, request or response bodies, or page
  snapshots.

## 9. Combined UI plus load result

While C5a ran 5 Locust users on the BFF (08:11:01 to 08:15:15 UTC), one browser
journey ran from 08:12:00 to 08:13:11 UTC.

* **It passed.** The answer streamed completely and appeared on the page, so the
  core user journey kept working under load.
* The user experience got noticeably worse. **The first streamed event took 30.2 s**
  (3.4 to 4.6 s without load) and the complete answer took 59.4 s (30.9 to 43.1 s
  without load).
* During that window, 4 to 5 of the Locust users were waiting on full Genie/SQL
  answers, which took 75 to 86 s each. This overlap in time is consistent with
  queueing ahead of the agent; it does not by itself prove the cause.
* The browser added 5 BFF calls and 1 extra agent invocation on top of the Locust
  load.

## 10. 403 findings (summary)

The full matrix is in [`403_TEST_MATRIX.md`](403_TEST_MATRIX.md).

* **No 403 was produced by any test today.**
* Each layer can be told apart from its response:
  * Apps proxy: `401 {}`, or a `302` to OIDC sign-in for a browser
  * FastAPI: `400`, `{error_code, message, request_id}`
  * Serving: `401 "Credential was not sent…"` with `WWW-Authenticate`, and
    `404 ENDPOINT_NOT_FOUND` for a wrong name
  * Unknown App API paths: `200` HTML (the single-page-app fallback)
* OBO works end to end. The Genie scope is present, so tracker item 5 is fixed in
  the current state. There is no throttling configuration, and no 429 responses
  occurred.
* Could not be verified: tracker items 4, 6 and 8, plus the least-privilege and
  permission-removal cases. They need a second identity or configuration changes,
  which were out of scope.

## 11. Stability and recovery assessment

| Question | Evidence | Assessment |
|---|---|---|
| Does throughput rise with load? | Serving: 1.67, then 6.44, then **6.32** answers per minute at 1, 5 and 10 users. BFF: chat turns per minute went from 6.8 (A4, mostly light turns) to 4.1 (E1). Full answers per minute went from 2.1 (C5a) to 2.7 (E1). | **Throughput levels off between 5 and 10 users.** At 10 users, extra concurrency turned into waiting time. |
| Does latency grow disproportionately? | Serving median ×1.16 at 5 users and ×2.24 at 10; p95 ×1.6 and ×2.76. BFF clarification median ×6.4 at 10 users. | Yes, at 10 users. |
| Do requests queue? | Clarifications, which also pass through the agent, went from about 8 s to 51.5 s. At the serving plateau, the number of requests in service at once is about 0.107/s × 33.5 s ≈ 3.6. | Queueing is **inferred** from the measured rates; the queue itself was not observed directly. |
| Is there throttling? | 0 × 429. No rate limits configured. | No |
| Does the failure rate rise? | 0 HTTP failures at every level. The app-level error share was not related to load (22 % at 5 users, 8 % at 10); it depends on which questions were drawn. | No |
| Does a downstream service dominate? | The direct serving path shows the same saturation without the BFF. BFF health calls stayed at a 0.25 to 0.3 s median at 10 users. | The **agent serving path dominates**. How time splits between Genie/SQL and the LLM inside the agent was **not measured**. |
| Is the laptop the constraint? | System CPU at most 49.5 %. The Locust process used at most 5.3 % CPU and 64 MB of memory. Free memory never fell below 11.4 GB. There was no CPU warning from Locust. | No |
| Does the system recover? | R1a, R1b and R1c were all at baseline, with no errors. | **Yes, fully.** |

## 12. Last stable and first degraded load

### 12.1 Comparison table (measured values only)

How to read the columns:
* **Requests** and **RPS** count every HTTP request in the stage.
* **p50, p95 and p99** are for the business call: `/api/chat` for the BFF, the
  invocation for serving, the complete-stream time for A5, and `/api/healthz`
  for A1.
* Where a stage has fewer than 20 samples, p95 and p99 equal the maximum.
* **[Retest]** rows: p50, p95 and p99 are for **full answers only** (`FULL_ANSWER`). The failure column shows HTTP failures, then business-outcome failures.
* **Failure rate** shows HTTP failures, then app-level `error` replies as a share
  of business calls.

| Component | Scenario | Users/workers | Spawn rate | Duration | Sessions | Sessions/sec | Requests | RPS | Failure rate | p50 | p95 | p99 | Result |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|---:|---|
| BFF | A1 health smoke | 1 | 1/s | 9.1 s | n/a | n/a | 7 | 0.77 | 0 % | 0.34 s | 1.04 s | 1.04 s | Pass |
| BFF | A2 business, single pass | 1 | 1/s | 97.7 s | 1 | 0.0102 | 6 | 0.061 | 0 % / 0 % | 84.5 s | 84.5 s | 84.5 s | Pass (1 full answer) |
| BFF | A3 business baseline | 1 | 1/s | 184 s | 1 | 0.0054 | 27 | 0.147 | 0 % / 25 % (1 of 4) | 8.1 s | 86.1 s | 86.1 s | Baseline (4 samples) |
| BFF | A4 business load | 5 | 1/s | 238.5 s | 5 | 0.021 | 195 | 0.818 | 0 % / 22 % (6 of 27) | 8.2 s | 71.4 s | 81.8 s | **Stable** |
| BFF | A5 streaming | 1 | 1/s | 67.6 s | not measured | not measured | 7 | 0.104 | 0 % | 7.2 s | 8.9 s | 8.9 s | Pass (first event p50 4.2 s) |
| BFF | C5a combined load | 5 | 1/s | 254 s | 5 | 0.0197 | 89 | 0.350 | 0 % / 23 % (3 of 13) | 74.6 s | 138.3 s | 138.3 s | Stable, with an early queueing signal |
| BFF | **E1 business load** | **10** | 1/s | 380.2 s | 10 | 0.0263 | 192 | 0.505 | 0 % / 8 % (2 of 26) | 107.7 s | 180.8 s | 195.8 s | **Degraded** |
| BFF | R1b recovery | 1 | 1/s | 180 s | 1 | 0.0056 | 18 | 0.100 | 0 % / 0 % | 52.9 s | 85.5 s | 85.5 s | Recovered |
| BFF **[Retest]** | P2-1 approved baseline | 1 | 1/s | 202.4 s | 4 | 0.020 | 8 | 0.040 | 0 % / 0 % | 47.4 s | 47.8 s | 47.8 s | Baseline: 4/4 completed (3 full answers) |
| BFF **[Retest]** | P2-2 approved load | 5 | 1/s | 359.4 s | 29 | 0.081 | 58 | 0.161 | 0 % / 0 % | 51.7 s | 84.3 s | 147.4 s | **Stable**: 29/29 completed |
| BFF **[Retest]** | P2-3 approved stress | **10** | 1/s | 393.7 s | 34 | 0.086 | 68 | 0.173 | 0 % / 0 % | 95.9 s | 135.6 s | 197.4 s | **Degraded**: 34/34 completed; flat throughput |
| BFF **[Retest]** | P2-4 approved recovery | 1 | 1/s | 196.2 s | 4 | 0.020 | 8 | 0.041 | 0 % / 0 % | 43.9 s | 48.6 s | 48.6 s | Recovered |
| Serving | B1 "Hello" | 1 | 1/s | 59 s | 1 | 0.017 | 1 | 0.017 | 0 % | 9.9 s | 9.9 s | 9.9 s | Pass |
| Serving | B2 business question | 1 | 1/s | 60 s | 1 | 0.017 | 1 | 0.017 | 0 % | 34.6 s | 34.6 s | 34.6 s | Pass |
| Serving | B3 baseline | 1 | 1/s | 180 s | 5 | 0.028 | 5 | 0.028 | 0 % | 33.5 s | 38.7 s | 38.7 s | Baseline |
| Serving | B4 load | 5 | 1/s | 214.3 s | 23 | 0.107 | 23 | 0.107 | 0 % | 38.7 s | 61.6 s | 71.5 s | **Stable** (early queueing) |
| Serving | **E3 load** | **10** | 1/s | 398.6 s | 42 | 0.105 | 42 | 0.105 | 0 % | 75.1 s | 106.7 s | 108.4 s | **Degraded** (throughput plateau) |
| Serving | R1a recovery | 1 | 1/s | 186 s | 5 | 0.027 | 5 | 0.027 | 0 % | 34.2 s | 40.0 s | 40.0 s | Recovered |
| UI | C1 landing smoke | 1 worker | n/a | 8.3 s | n/a | n/a | 1 test | n/a | 0 % | 8.3 s | n/a | n/a | Pass |
| UI | C2 and C3 chat (4 sequential) | 1 worker | n/a | 38.7 to 48.7 s each | 4 | not measured | 4 journeys | n/a | 0 % | 43.1 s (stream complete, C3) | n/a | n/a | Pass |
| UI | C4 chat (2 concurrent) | 2 workers | n/a | 43.7 and 64.2 s | 2 | not measured | 2 journeys | n/a | 0 % | 30.9 and 40.8 s (stream complete) | n/a | n/a | Pass |
| UI | C5b chat during 5-user load | 1 worker | n/a | 67.1 s | 1 | not measured | 1 journey | n/a | 0 % | 59.4 s (stream complete; first event 30.2 s) | n/a | n/a | Pass, degraded experience |
| UI | R1c recovery | 1 worker | n/a | 52.8 s | 1 | not measured | 1 journey | n/a | 0 % | 38.2 s (stream complete; first event 3.8 s) | n/a | n/a | Pass, recovered |

### 12.2 Summary by component

| | BFF (`basic_scenario.py`) | Direct serving (KCC SS27 question) |
|---|---|---|
| **Last stable tested level** | **5 users**: 195 requests with 0 failures; clarifications about 8 s; full answers 71 to 82 s, against a baseline of 84 to 86 s. With a heavier mix of questions (C5a), full answers had a median of 80 s but reached 138 s, and the UI's first event took 30 s: an early warning. | **5 users**: 23 of 23 valid; median 38.7 s (×1.16); p95 61.6 s (×1.6); 6.44 answers per minute |
| **First degraded tested level** | **10 users**: chat p95 180.8 s (×2.1); full answers median 113 s; clarifications median 51.5 s (×6.4) | **10 users**: median 75.1 s (×2.24); p95 106.7 s (×2.76, near the 3 × stop limit); throughput flat at 6.32 per minute |
| **Saturation signal** | Rising latency with no errors | Throughput plateau plus latency growth in proportion to concurrency |
| **Recovery** | Full (R1b) | Full (R1a) |

**These are the limits observed under this test's conditions:** one identity, the
repository's question sets, runs of 3 to 5 minutes, and a laptop load generator.
They are not a certified capacity figure. The system was **not** pushed to failure:
no errors occurred at the highest approved level.

## 13. Bottleneck analysis

> **[Retest] Confirmed on 25 Sep by the serving traces (section 0.13).** At 10 users the median wait
> before the agent started was 55.6 s. LLM, Genie and AI.Vision times did not change, CPU was not a
> factor, and at most 4 to 5 agent runs executed at once (provisioned concurrency 4). The
> "Not yet shown" items below are answered there, apart from the SQL warehouse history and the App
> compute metrics.

**Most likely bottleneck (inferred, not confirmed):** the agent serving endpoint's
capacity to process requests concurrently. All traffic goes to one Small CPU
served entity.

Supporting evidence:
1. **Configuration:** `traffic_config` sends 100 % of traffic to
   `lakehouse_dev-ds_insights_companion_lhdev-agent_89`, workload size **Small**,
   CPU. Databricks documents the Small workload size as provisioning concurrency
   of roughly up to 4 requests; the exact value for this entity should be confirmed
   from the endpoint's metrics.
2. **Throughput levels off** at 6.3 to 6.4 answers per minute from 5 to 10 users,
   while latency roughly doubles. Little's law gives about 3.6 requests in service
   at once (0.107 per second × 33.5 s service time), which fits a limit of about 4.
3. **The BFF tier stayed responsive.** At 10 users, `/api/healthz`, `/api/me` and
   `/api/sessions` stayed at 0.25 to 0.45 s. The App ran MEDIUM compute with no 5xx.
4. **The same degradation appears without the BFF** (E3 goes directly to serving).
5. **The UI's added overhead is small:** its complete stream matches the direct
   serving time within a few seconds.
6. **The load generator was not a constraint.**
7. **No throttling:** 0 × 429, and no rate limits are configured.

Not yet shown, and needed before naming a root cause:
* Serving endpoint metrics for the test windows (08:01 to 08:05, 08:25 to 08:39
  UTC): provisioned concurrency, request queueing or latency, CPU and replica count.
* Genie space and SQL warehouse query history for the same windows (queueing, and
  how long each statement took).
* LLM endpoint latency within the agent (the agent's own traces or logs).
* App compute metrics for the BFF: CPU, memory and worker usage.

## 14. Risks and limitations

1. **One identity.** Every result is for one user who holds `CAN_MANAGE`. Behaviour
   for other users or across users is untested (tracker items 6 and 8; M18 and M19).
2. **[Retest: addressed]** The approved-question retest (section 0) replaced the generic questions and confirmed the same stable and degraded levels. Original text: **The question mix drives results.** The generic sample questions produce 38 %
   clarifications and 16 % refusals, so BFF load under-represents the full-answer
   workload. The E1 mix happened to be answer-heavy. BFF throughput is therefore
   not directly comparable across stages.
3. **[Retest: fixed]** `basic_scenario.py` now uses `chat_outcome.py`, and error turns fail. Original text: **The Locust scenarios overstate success.** They count `action: "error"` as a
   pass (gap G1). This report corrected for it using the audit data.
4. **Locust CSV files leave out requests that finish during the grace period.** 0 to
   2 requests per stage, usually the slowest chat calls, are missing from
   `locust_stats.csv`. **The audit records (`requests.jsonl`) are the source for
   every figure here.** The Locust HTML reports do include these requests.
5. **Small samples.** Baselines have 4 to 5 samples. p95 and p99 figures for stages
   with fewer than 20 samples equal the maximum.
6. **Short duration.** No soak test was run (the longest was about 7 minutes), so
   token expiry after 60 minutes, memory growth and long-run stability are
   untested.
7. **Not taken beyond degradation.** Behaviour between 10 and 20 users or more (E2
   and E4) is unknown.
8. **The laptop runs the load**, so network latency to the workspace is included in
   every figure.
9. **Cost and data.** About 165 agent invocations were made (77 direct serving
   calls, 73 BFF chat turns, 7 streams and 8 UI journeys), each involving Genie,
   SQL or LLM work, and about 30 BFF conversations were created under the test
   identity. That user now has 57 sessions listed. No cleanup was done, because the
   repository has no documented cleanup method for test-owned data.

## 15. Recommendations

> **[Retest]** New items from section 0:
> * **High.** Grant the test user ProductReviews access, or confirm that the restriction
>   is intended, then re-screen Q17 to Q21.
> * **High.** Investigate why FinanceInsights returns zero records for all six approved
>   questions: data not loaded, filters, or row-level permission. Each such answer takes
>   1.5 to 2.5 minutes to say "no data".
> * **High.** Return data-access failures in a way clients can detect. They currently
>   arrive as HTTP 200 with `action: error`.
> * **Medium.** Review how reproducible the multi-domain figures are (Q43's scope varied).
> * Recommendation 3 below is done for the test code. Recommendation 4 is no longer
>   reproduced with approved questions.

**Critical:** none identified. No data leakage, authorization defect or instability
was observed.

**High**
1. **Increase and confirm serving capacity**, then repeat E3 at 10 and 20 users.
   Options include a larger workload size or provisioned concurrency for the entity
   taking 100 % of traffic, or spreading traffic across entities. Monitor the
   endpoint metrics while the test runs.
2. **Least-privilege and multi-identity testing.** Provide at least two test users
   without `CAN_MANAGE` (one with and one without Genie or warehouse access) to
   close tracker items 6 and 8 and matrix rows M18 and M19.
3. **Fix the test validation (gap G1)** so that `action: "error"` counts as a
   failure. Add a set of in-domain business questions (for example the KCC SS27
   question already in the UI test) so load reflects real usage.
4. **Investigate routing consistency.** The same question was sometimes refused and
   sometimes answered in full. Refusals and clarifications are 54 % of turns with
   the sample questions.

**Medium**
5. **User experience under queueing.** The UI waited 30 s before the first streamed
   event at 5 concurrent heavy users. Consider an early "queued or working" status
   event from the BFF, and a user-facing timeout message.
6. **Add client timeouts to the BFF scenarios (gap G2)**, and record the
   `session_id` in the stream scenario so streaming sessions can be counted.
7. **Observability for 403 triage (tracker item xx).** Log and show the
   `request_id` and `ReqId` values. Use the response signature table to classify
   incidents.
8. **Cost hygiene.** Five served entities receive 0 % of traffic with scale-to-zero
   disabled. Confirm whether they are still needed.

**Low**
9. Return a JSON `404` for unknown `/api/*` paths instead of the single-page-app
   HTML (M06).
10. Run a 60-minute soak test at 3 to 5 users to cover OBO token expiry (tracker
    item 1) and long-run stability.
11. Agree formal pass thresholds for full-answer latency. The repository default of
    5 s p95 in `config/app-settings.json` is not realistic for agent answers.

## 16. Evidence and report links

All paths are relative to
[`results/final-assessment/20260924-131117/`](../results/final-assessment/20260924-131117/).

| Evidence | Path |
|---|---|
| Execution plan | [`execution-plan.md`](../results/final-assessment/20260924-131117/execution-plan.md) |
| Sanitized command log | [`command-log.md`](../results/final-assessment/20260924-131117/command-log.md) |
| Machine-readable summary (all stages, post-hoc guard check) | [`final-summary.json`](../results/final-assessment/20260924-131117/final-summary.json) |
| Evidence index | [`README.md`](../results/final-assessment/20260924-131117/README.md) |
| Locust HTML reports | `stages/<stage>/locust.html`, for example [`E1`](../results/final-assessment/20260924-131117/stages/E1-bff-load-u10/locust.html) and [`E3`](../results/final-assessment/20260924-131117/stages/E3-serving-load-u10/locust.html) |
| Locust CSV files | `stages/<stage>/locust_stats.csv`, `_failures.csv`, `_exceptions.csv`, `_stats_history.csv` |
| Audit records per request | `stages/<stage>/requests.jsonl`, `usage.jsonl`, `guard.json`, `summary.json`, `manifest.json`, `console.log` (redacted) |
| Playwright HTML reports | `stages/C*/html-report/`, `stages/R1c-ui-chat-recovery/html-report/`. Open with `npx playwright show-report <path>`. |
| Playwright JSON and trace timings | `stages/C*/results.json`, `trace-timings.json`. Cleaned traces are in `artifacts/**/trace.zip`. |
| Auth probes | [`stages/D1-auth-matrix-probes/`](../results/final-assessment/20260924-131117/stages/D1-auth-matrix-probes/) |
| Tools used | [`instrumentation/`](../results/final-assessment/20260924-131117/instrumentation/): `run_stage.py`, `audit_plugin.py`, `analyze_stage.py`, `trace_timings.py`, `sanitize_traces.py`, `probe_auth_matrix.py` |
| **[Retest]** Approved-question retest | [`results/bff-valid-question-retest/20260924-115127/`](../results/bff-valid-question-retest/20260924-115127/): `phase1-screening/final/`, `stages/P2-*/` (Locust HTML and CSV, `requests.jsonl`, `summary.json`), `consistency/`, `workload/phase2-workload.json`, `failure-evidence/`, `final-summary.json`, `command-log.md` |
| Historical evidence | `results/20260922-164849-react_ui-66e60a/` (expired-session failure), `results/report_*` (2026-09-21, 212 × 401), `results/cli/20260924-*` (the user's runbook runs from earlier today) |

A secret scan of the whole evidence folder found no JWTs, PATs, cookie values or
user email, including inside the zip archives.

## Appendix A: Commands executed

The full sanitized list, with timestamps, is in `command-log.md`. The patterns
were as follows (the token is always passed through the environment and never
appears in a command):

```text
# Locust stage (run_stage.py mints the OAuth U2M token in-process, then runs):
python -m locust --config config/<profile>.conf -f <scenario>,<assessment>/instrumentation/audit_plugin.py \
  --csv <stage>/locust --csv-full-history --html <stage>/locust.html [-u N -r R -t T -s GRACE]

# Serving stages additionally: BIC_TEST_USER_ID=<SCIM Me of the same token, redacted>
#   BIC_TEST_QUESTION='How many articles do we have in Training KCC for SS27?' (B2 to E3, R1a)
#   BIC_SESSION_ID_PREFIX=final_assess_20260924

# Playwright stage:
PLAYWRIGHT_HTML_OUTPUT_DIR=<stage>/html-report PLAYWRIGHT_JSON_OUTPUT_NAME=<stage>/results.json PLAYWRIGHT_HTML_OPEN=never \
  npx playwright test tests/<spec> --project=chromium --workers=<1|2> [--repeat-each=N] [--trace on] \
  --output <stage>/artifacts --reporter "list,html,json"

# Auth probes and read-only metadata:
python instrumentation/probe_auth_matrix.py stages/D1-auth-matrix-probes/probes.json
```

| Stage | Profile and overrides |
|---|---|
| A1 | `locust.deployed-smoke.conf` |
| A2 | `locust.deployed-stress.conf -u 1 -r 1 -t 90s -s 180` |
| A3 | `locust.deployed-stress.conf -u 1 -r 1 -t 3m -s 120` |
| A4 | `locust.deployed-stress.conf -u 5 -r 1 -t 3m -s 120` |
| A5 | `locust.deployed-stream.conf -s 120` |
| B1 | `locust.serving-smoke.conf -t 60s -s 190` (`BIC_TEST_QUESTION` unset) |
| B2 | `locust.serving-smoke.conf -t 60s -s 190` (KCC question) |
| B3 | `locust.serving-stress.conf -u 1 -r 1 -t 3m -s 120` |
| B4 | `locust.serving-stress.conf -u 5 -r 1 -t 3m -s 120` |
| C1 | `bic-smoke.spec.ts --workers=1` |
| C2 | `bic-chat-complete.spec.ts --workers=1` |
| C3 | `bic-chat-complete.spec.ts --repeat-each=3 --workers=1 --trace on` |
| C4 | `bic-chat-complete.spec.ts --repeat-each=2 --workers=2 --trace on` |
| C5a / C5b | A4 profile, plus `bic-chat-complete.spec.ts --workers=1 --trace on` started 60 s later |
| E1 | `locust.deployed-stress.conf -u 10 -r 1 -t 5m -s 180` |
| E3 | `locust.serving-stress.conf -u 10 -r 1 -t 5m -s 190` |
| R1a | `locust.serving-stress.conf -u 1 -r 1 -t 3m -s 120` |
| R1b | `locust.deployed-stress.conf -u 1 -r 1 -t 3m -s 120` |
| R1c | `bic-chat-complete.spec.ts --workers=1 --trace on` |

A self-test of the audit add-on ran first, against a throwaway **local** HTTP server
(`127.0.0.1:8765`). It sent no traffic to deployed services.

## Appendix B: Skipped tests and reasons

| Test | Reason |
|---|---|
| E2: BFF 20 users, 10 min | Not approved. The approved scope was E1 + E3 + recovery. |
| E4: serving 15 to 20 users | Not approved |
| C6: combined run at the highest stable level | The highest stable level was 5 users, which C5 had already covered. Skipped as a duplicate. |
| Headed (visible) browser runs | Evidence runs were headless. Headed mode affects only visibility, not behaviour. |
| Expired API token test (M16 live) | No already-expired token was available. Historical evidence was used instead. |
| Wrong-workspace token (M17) | No approved credential |
| Least-privilege or downstream-denied user (M18) | No such identity exists. No permission changes were allowed. |
| Missing CAN USE or CAN QUERY (M19) | Permission changes were not authorized |
| Tracker item 3 (production access group) | Production is out of scope |
| Tracker items 4, 6 and 8 reproduction | Would need a deployment, scope changes or several identities, none of which were authorized |
| `/api/schema`, `/api/table/sort`, `/api/query-feedback`, `/api/query-metrics`, `/api/historical-query` | Not covered by the repository's scenarios, and no new scenarios were invented |
| Cleanup of test conversations | The repository has no documented cleanup method for test-owned data. No data was deleted. |
| **[Retest]** ProductReviews questions Q17 to Q21 in load | The test user has no access (access-coverage limitation) |
| **[Retest]** FinanceInsights questions Q22 to Q27 in load | No usable data returned (data availability or permission requires investigation) |
| **[Retest]** Q15 in load | Clarification response |
| **[Retest]** Re-running the 403 matrix, serving, streaming and Playwright tests | Not requested, and no new BFF issue needed them |

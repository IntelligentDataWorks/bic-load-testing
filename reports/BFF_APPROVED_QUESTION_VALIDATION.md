# BFF Approved-Question Validation and Retest

**Date:** 24 September 2026. Phase 1 screening 11:54 to 12:50 UTC; Phase 2 load 13:06 to 13:27 UTC; consistency 13:27 to 13:43 UTC.
**Target:** deployed FastAPI BFF, `POST /api/chat` on
`https://ds-insights-companion-ui-809065969263152.aws.databricksapps.com` (`app_env: dev`,
contract 1.1.0). Development only.
**Identity:** one real user, Databricks OAuth U2M token, `auth_mode: obo`.
**Evidence:** [`results/bff-valid-question-retest/20260924-115127/`](../results/bff-valid-question-retest/20260924-115127/)

## Summary

| | Result |
|---|---|
| Questions screened | **43 of 43**, each once, one user, fresh session, 5 s pause |
| Completed business outcomes (result of record) | **31 of 43 (72.1%)**: 16 full data answers, 15 valid direct responses |
| Excluded from load | **12**: ProductReviews ×5 (access), FinanceInsights ×6 (no usable data), RangeInsights Q15 (clarification). Q17 was also a clarification but is counted under ProductReviews. |
| Original 80% gate | Not met (72.1%). **The requester then removed the gate**, ruling that inaccessible or unavailable domains must not block the accessible ones. |
| Phase 2 load (§12) | Run on the 31 completed questions only: 1, 5 and 10 users, then 1-user recovery. **71 of 71 chat turns completed**, with 0 HTTP failures. **Last stable: 5 users. First degraded: 10 users.** |
| Consistency (§7) | 20 of 20 repeats were full answers: **100% consistent** for Q02, Q06, Q12 and Q43 |
| Scope of the capacity result | **Only the accessible, usable domains** (AI.Vision, ShareOfSearch, RangeInsights, ProductBrief, ProductBriefFootball, Chitchat), all under **one authenticated identity**. **No claim is made about ProductReviews or FinanceInsights scalability.** |

The gate was missed because of two whole domains, not because of load or instability:

* **ProductReviews: 0 of 5.** Four questions returned *"You don't have access to the
  'ProductReviews' data source. Contact your workspace admin to request access."* The fifth
  (Q17) asked a clarifying question.
* **FinanceInsights: 0 of 6.** All six ran SQL and came back with an answer saying that no
  data is available (zero records).

The other seven domains completed **31 of 32** questions. The exception is RangeInsights
Q15, which got a clarifying question.

---

## 1. Question catalogue and source check

* Catalogue: [`data/approved_questions.txt`](../data/approved_questions.txt). It uses the
  existing `data/*.txt` convention (UTF-8, `#` comments, one question per line) and adds
  `id|domain|kind|question[|subjects]`. IDs Q01 to Q43 follow the order you gave.
* All 43 questions match the `routing_examples` and `multi_domain_examples` in
  `lak-ds-insights-companion/configs/orchestrator.dev.yaml` **character for character**,
  including the em dash in Q11. The YAML contains no extra examples.

**Discrepancies recorded; your list was used as supplied:**
1. The local YAML is at commit `4da26de` (10 Sep 2026). The app was last deployed on 23 Sep
   2026, so the deployed configuration may be newer. It could not be read from the
   deployment.
2. In the YAML's multi-domain example, the "share of search" sub-question is assigned to
   `AI.Vision`, not `ShareOfSearch`. In the test, Q43 still returned share-of-search rows.
3. `ProductReviews` has `skip_refiner: true`, yet Q17 got a refiner-style clarifying
   question. The YAML says the refiner runs *before* classification, which may explain it.
4. A second, older `orchestrator.yaml` exists in `Downloads/IRIS/BIC/configs/` (24
   examples, June 2026). It was ignored as not authoritative.

## 2. How responses were classified

HTTP 200 is not treated as success. Each turn gets exactly one classification from
[`scenarios/chat_outcome.py`](../scenarios/chat_outcome.py). It reads the ChatResult fields
that the BFF sets in `to_chat_result` (`backend/orchestrator.py`): `action`, `message`,
`insighter.insight`, `text2sql.sql_query`, `text2sql.sql_data` and
`followup_query_suggestions`.

| Classification | Rule | Counts as |
|---|---|---|
| `FULL_ANSWER` | `summarized`, non-empty `insighter.insight`, at least one `sql_data` row. For multi-domain questions, every requested subject must also appear (whole words) in the answer, evidence or column names. | **Completed** |
| `VALID_DIRECT_RESPONSE` | `return_response` with a non-empty `message`, for chitchat, definition or product-brief questions | **Completed** |
| `CLARIFICATION` | `clarification_needed` with a question in `message` | Incomplete |
| `PARTIAL_ANSWER` | Multi-domain answer that leaves out a requested subject | Incomplete |
| `ROUTING_REFUSAL` | `error` whose message starts with a fixed router template (*"I could not tell which data…"*, *"This query does not fall within the supported data domains"*), or a document returned for a data question | Failed |
| `APPLICATION_ERROR` | Any other `error`. The reason is named where the message is a known template: `no_data_access`, `genie_status`, `bff_unexpected_response`, `unparsed_action:<x>`, and so on. | Failed |
| `EMPTY_RESPONSE` | Empty answer or clarification, or `summarized` with 0 rows | Failed |
| `INCOMPLETE_STREAM` | SSE stream with no terminal `result` event (only for `/api/chat/stream`, which was not used here) | Failed |
| `HTTP_ERROR` / `TIMEOUT` | Non-200 status, a 504 or `upstream_timeout`, a client timeout (330 s), or a dropped connection | Failed |
| `INVALID_CONTRACT` | Body is not JSON, or `session_id`, `user_query_id` or a valid `action` is missing | Failed |

**Follow-up suggestions are recorded separately and never count as the answer.** A turn with
suggestions but no primary answer is `EMPTY_RESPONSE` and is flagged
`followups_without_primary`. **This happened 0 times.** Every `summarized` turn had 3
suggestions, including the six FinanceInsights "no data" answers.

**Manual review (4 turns).** Q22, Q23, Q26 and Q27 met the automatic `FULL_ANSWER` rule,
because each had one SQL row. On review, that row is a record-count probe (for example
`total_rows`, or `min_key_date` / `max_key_date`) and the answer says that no data exists.
They were relabelled `EMPTY_RESPONSE (no_data_available, reviewed)`, marked ‡ below.
The review read each stored turn back through `GET /api/session-chat`, printed a masked
excerpt with every digit shown as `#`, and saved nothing. This case needs content review:
a legitimate one-row answer can also contain zeros (for example "0 articles").

`python -m pytest tests/python -q`: **24 passed** (classifier and catalogue tests, run before
screening and again after the `no_data_access` reason was added).

## 3. Results by question (result of record)

† **Laptop standby.** On the first attempt the load-generator laptop went into Windows Modern
Standby. Each of these questions was re-run once, and the re-run is shown (see §6).
‡ **Relabelled after manual review** (§2).
Durations are client-measured to the complete JSON response. Answer text is not stored;
only its length is.

| ID | Domain | Question | HTTP | Action | Classification | Primary answer captured | Follow-up suggestions | SQL/data evidence | Duration (s) | Session ID | Result |
|---|---|---|---:|---|---|---|---:|---|---:|---|---|
| Q01 † | AI.Vision | How is You got this slogan recognized amongst consumers in Q3 2025 in germany? | 200 | `summarized` | FULL_ANSWER | yes, 380 chars | 3 | SQL; 1 row (`slogan_name`, `total_responses`, `yes_count`, …) | 172.5 | `lt-169f53359f6243c490c07c5adbd98886` | PASS |
| Q02 | AI.Vision | List the top 5 brands by purchase consideration in AU (Australia) for Q4 2024. | 200 | `summarized` | FULL_ANSWER | yes, 375 chars | 3 | SQL; 5 rows (`brand_name`, `consideration_pct`) | 51.0 | `lt-a877ffee6ffc45ceb184354a40cbc47c` | PASS |
| Q03 | AI.Vision | What is the difference in unaided brand awareness, all mentions between for male and female consumers in the united states of america, Q3 2025. | 200 | `summarized` | FULL_ANSWER | yes, 221 chars | 3 | SQL; 1 row (`male_awareness_pct`, `female_awareness_pct`, `difference_pp`) | 47.0 | `lt-83caf190993548bb91144618dbb80aa4` | PASS |
| Q04 | AI.Vision | What is the brand familiarity for Nike in IN (India) in Q2 2024? | 200 | `summarized` | FULL_ANSWER | yes, 304 chars | 3 | SQL; 1 row (`brand`, `country`, `quarter`, …) | 45.3 | `lt-ef995e70249043e7b65e9723ddb6dc97` | PASS |
| Q05 † | AI.Vision | What is the brand future purchase intent for Lululemon in Training globally (Global 10) in Q3 2025 and what is the most strongly associated CEP for Lululemon | 200 | `summarized` | FULL_ANSWER | yes, 367 chars | 3 | SQL; 2 rows (`metric_type`, `value_pct`, `cep_code`, …) | 68.5 | `lt-1140adec7ded466f8bb2829f9e9de038` | PASS |
| Q06 | ShareOfSearch | What is the Q1 2025 brand share of search for adidas, nike and lululemon in Germany? | 200 | `summarized` | FULL_ANSWER | yes, 278 chars | 3 | SQL; 3 rows (`country`, `brand`, `share_of_search`) | 35.7 | `lt-5a823efe3f704f5bbe06d42ac9b1c9f5` | PASS |
| Q07 | ShareOfSearch | Which category saw the largest growth in search volume for adidas and Nike in 2024? | 200 | `summarized` | FULL_ANSWER | yes, 367 chars | 3 | SQL; 12 rows (`brand`, `category_from_filter`, `sv_2023`, …) | 41.1 | `lt-dbb60659b5ae400890265a2cb41bdf97` | PASS |
| Q08 | ShareOfSearch | Who leads in Trail Running search volume in Running vs Outdoor? | 200 | `summarized` | FULL_ANSWER | yes, 374 chars | 3 | SQL; 2 rows (`category`, `total_search_volume`) | 33.8 | `lt-4469dc274e804f87bd94967bf530f7f8` | PASS |
| Q09 | ShareOfSearch | Top adidas partner in Lifestyle for H1 2025 in EU | 200 | `summarized` | FULL_ANSWER | yes, 192 chars | 3 | SQL; 1 row (`partner`, `total_search_volume`) | 31.4 | `lt-801cf5f993024e1aa9f48f1e43f6091e` | PASS |
| Q10 | ShareOfSearch | Which market saw the highest growth in adidas search volume in Q1 2025 compared to Q1 2024? | 200 | `summarized` | FULL_ANSWER | yes, 378 chars | 3 | SQL; 5 rows (`market`, `q1_2024`, `q1_2025`, …) | 46.7 | `lt-714cc15ae6fd403b9fe8969eb762d9d4` | PASS |
| Q11 | RangeInsights | Show me the biggest 10 sales lines that existed in SS26 but have zero articles in SS27 for Sportswear APP Women — and what was their MBV in SS26. | 200 | `summarized` | FULL_ANSWER | yes, 416 chars | 3 | SQL; 3 rows (`sales_line`, `ss26_article_count`, `ss26_mbv`, …) | 49.7 | `lt-38b2c32636ef4907a2a0277d1275ef00` | PASS |
| Q12 | RangeInsights | How many articles do we have in Training KCC for SS27? | 200 | `summarized` | FULL_ANSWER | yes, 262 chars | 3 | SQL; 1 row (`article_count`) | 37.7 | `lt-1b5a19c9b0654b66ac359de8f634b83a` | PASS |
| Q13 | RangeInsights | How many articles of Specialist Sports, Tennis FTW Women, FW26 are currently not open for ranging? | 200 | `summarized` | FULL_ANSWER | yes, 336 chars | 3 | SQL; 1 row (`articles_not_open_for_ranging`) | 39.1 | `lt-a58857f7eb28431b8de8308eb04b1509` | PASS |
| Q14 | RangeInsights | What is the total article count for SS27? | 200 | `summarized` | FULL_ANSWER | yes, 143 chars | 3 | SQL; 1 row (`total_article_count`) | 41.7 | `lt-8e9f522e7f0648bca81cb825a2993895` | PASS |
| Q15 | RangeInsights | What is the best performing article for FW26 range in NAM? | 200 | `clarification_needed` | CLARIFICATION | no (clarifying question) | 0 | not applicable | 8.2 | `lt-e11a4468d91b4da2b2c773c3c6951857` | INCOMPLETE |
| Q16 | RangeInsights | Can you show me the article and Model number and the RRP for the Sawe Collection Pack adizero shoes? | 200 | `summarized` | FULL_ANSWER | yes, 293 chars | 3 | SQL; 3 rows (`art_number`, `art_mdl_number`, `art_collection_pack`, …) | 38.8 | `lt-83d106a481434a43933d0feb38793fb4` | PASS |
| Q17 | ProductReviews | What is the consumer sentiment breakdown by market? | 200 | `clarification_needed` | CLARIFICATION | no (clarifying question) | 0 | not applicable | 6.9 | `lt-d1ea4a3c3da840dc88f66070cd810c58` | INCOMPLETE |
| Q18 | ProductReviews | Which product is having the highest number of negative feedback? | 200 | `error` | APPLICATION_ERROR | no (error message) | 0 | not applicable | 8.2 | `lt-4ab3651732fb41e5a6397c8dab67e88c` | FAIL |
| Q19 | ProductReviews | What are the top 5 negative aspects of Samba for EU in 2026? | 200 | `error` | APPLICATION_ERROR | no (error message) | 0 | not applicable | 9.5 | `lt-2c217f2da3da4e119b2c02a736f42da6` | FAIL |
| Q20 | ProductReviews | What are the top 10 products with the highest number of reviews in 2025, and what is their average rating? | 200 | `error` | APPLICATION_ERROR | no (error message) | 0 | not applicable | 9.0 | `lt-e1ae1fb72a7a44f686ad89568bbe0b07` | FAIL |
| Q21 | ProductReviews | Show the sentiment trend for Hyperboost in the first 3 months after its first review date. Are early adopters more positive or negative? | 200 | `error` | APPLICATION_ERROR | no (error message) | 0 | not applicable | 8.9 | `lt-896863b8c1644e739a99ea7b8e6b88fa` | FAIL |
| Q22 | FinanceInsights | please give net sales for backlog for Mirror Season in NAM | 200 | `summarized` | EMPTY_RESPONSE ‡ | no: says no data (336 chars) | 3 | SQL; 1 row (`total_rows`, `distinct_markets`, `distinct_seasons`) | 110.3 | `lt-14ee77f3cd8c417b8f5aa4a0f9b80bd5` | FAIL |
| Q23 | FinanceInsights | give me net sales by article for last year | 200 | `summarized` | EMPTY_RESPONSE ‡ | no: says no data (246 chars) | 3 | SQL; 1 row (`min_key_date`, `max_key_date`, `distinct_dates`, …) | 93.8 | `lt-9c4f4f5569c841ac967fa21052f726c1` | FAIL |
| Q24 | FinanceInsights | Net Sales by Market for Mirror Season (MS). | 200 | `summarized` | EMPTY_RESPONSE | no: says no data (597 chars) | 3 | SQL; 0 rows | 159.1 | `lt-f28f3399502f41f7865a79f5fc58232f` | FAIL |
| Q25 | FinanceInsights | please give net sales by Key Category Cluster for Business on Hand (BOH) | 200 | `summarized` | EMPTY_RESPONSE | no: says no data (584 chars) | 3 | SQL; 0 rows | 106.5 | `lt-a16fe05e452f4f0fbeb7537b06fda8ff` | FAIL |
| Q26 † | FinanceInsights | Top 20 Articles by Net Sales for BOH by Key Category Cluster | 200 | `summarized` | EMPTY_RESPONSE ‡ | no: says no data (359 chars) | 3 | SQL; 1 row (`total_rows`) | 108.9 | `lt-7e04aa186171468cafe00e6840647739` | FAIL |
| Q27 † | FinanceInsights | pls give Net Sales (NS) and Net Quantity (NQ) for TIRO | 200 | `summarized` | EMPTY_RESPONSE ‡ | no: says no data (340 chars) | 3 | SQL; 1 row (`row_count`, `net_sales_local`, `net_quantity`) | 108.2 | `lt-2effb8cf33134ed8a262aef19efa1348` | FAIL |
| Q28 | ProductBrief | Help me make a product brief for a running shoe for SS27 London Marathon | 200 | `return_response` | VALID_DIRECT_RESPONSE | yes, 8266 chars | 0 | not applicable | 68.5 | `lt-853b0d57f5fa41af870626de1733ff11` | PASS |
| Q29 | ProductBrief | Create a product brief for the Adizero Adios Pro Evo 3 for SS27 | 200 | `return_response` | VALID_DIRECT_RESPONSE | yes, 8098 chars | 0 | not applicable | 58.4 | `lt-550c959e1e2a400f880e65e78579f056` | PASS |
| Q30 | ProductBrief | Write a brief for the SS27 running campaign around the London Marathon | 200 | `return_response` | VALID_DIRECT_RESPONSE | yes, 7746 chars | 0 | not applicable | 62.1 | `lt-19686ea05a9d41ea8592c31023cf90fa` | PASS |
| Q31 | ProductBrief | Can you draft a product brief for our top running shoe launch in Spring 2027? | 200 | `return_response` | VALID_DIRECT_RESPONSE | yes, 8177 chars | 0 | not applicable | 63.4 | `lt-42dd43e2e8824eeaaa8fc26fdff8d8e9` | PASS |
| Q32 | ProductBriefFootball | Write me a product brief for Manchester United 3rd jersey for the 2027/2028 season | 200 | `return_response` | VALID_DIRECT_RESPONSE | yes, 8692 chars | 0 | not applicable | 61.3 | `lt-36394106a5ee4d9bae99d625fdf26ba1` | PASS |
| Q33 | ProductBriefFootball | Draft a product brief for the Man United third kit for 2027/28 | 200 | `return_response` | VALID_DIRECT_RESPONSE | yes, 8868 chars | 0 | not applicable | 59.0 | `lt-ee54e901fbba49b999d2480b2ee695dd` | PASS |
| Q34 | ProductBriefFootball | Create a brief for the Manchester United away jersey launch | 200 | `return_response` | VALID_DIRECT_RESPONSE | yes, 8713 chars | 0 | not applicable | 59.8 | `lt-3456af63826d4535aef2c3bfe6fd8fa6` | PASS |
| Q35 | Chitchat | hi | 200 | `return_response` | VALID_DIRECT_RESPONSE | yes, 528 chars | 0 | not applicable | 10.8 | `lt-141f0e1f912140b9aa8767152aa832b6` | PASS |
| Q36 | Chitchat | hello there | 200 | `return_response` | VALID_DIRECT_RESPONSE | yes, 304 chars | 0 | not applicable | 10.0 | `lt-974f9fad73074a1eafc2b4b559e61245` | PASS |
| Q37 † | Chitchat | thanks! | 200 | `return_response` | VALID_DIRECT_RESPONSE | yes, 325 chars | 0 | not applicable | 10.1 | `lt-d12a673b57834ce796b555145d6b3a91` | PASS |
| Q38 | Chitchat | what can you do | 200 | `return_response` | VALID_DIRECT_RESPONSE | yes, 1215 chars | 0 | not applicable | 12.6 | `lt-d0722cd5b82943afaca7d4f45c418dee` | PASS |
| Q39 | Chitchat | what kinds of questions can I ask you? | 200 | `return_response` | VALID_DIRECT_RESPONSE | yes, 1033 chars | 0 | not applicable | 13.2 | `lt-54722593c8e842ad9f288653bb908cd6` | PASS |
| Q40 | Chitchat | what does MBV mean | 200 | `return_response` | VALID_DIRECT_RESPONSE | yes, 536 chars | 0 | not applicable | 12.3 | `lt-2ab8eb722b654979919a1f75a9187e26` | PASS |
| Q41 | Chitchat | what does BOH stand for? | 200 | `return_response` | VALID_DIRECT_RESPONSE | yes, 407 chars | 0 | not applicable | 13.1 | `lt-bb26c22e5d074b439106324ca22cbd81` | PASS |
| Q42 | Chitchat | define Net Sales | 200 | `return_response` | VALID_DIRECT_RESPONSE | yes, 594 chars | 0 | not applicable | 11.4 | `lt-28fded15a91041a1b3b4911cc2546c6c` | PASS |
| Q43 | Multi-Domain | What is the MBV of Samba in SS26 and how does Samba rank in share of search in Germany? | 200 | `summarized` | FULL_ANSWER | yes, 199 chars | 3 | SQL; 20 rows (`rank`, `franchise`, `brand`, …) | 49.8 | `lt-8b0f5f09aaf346ed8c10919e6e89b80f` | PASS |

## 4. Results by domain

| Domain | Questions | Completed | Clarification | Refusal / error / empty | Median, all turns (s) | p95, all turns (s)\* | Median, completed (s) | Result |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| AI.Vision | 5 | 5 | 0 | 0 | 51.0 | 172.5 | 51.0 | Pass |
| ShareOfSearch | 5 | 5 | 0 | 0 | 35.7 | 46.7 | 35.7 | Pass |
| RangeInsights | 6 | 5 | 1 (Q15) | 0 | 38.8 | 49.7 | 39.1 | Pass with 1 clarification |
| ProductReviews | 5 | **0** | 1 (Q17) | 4 (no access) | 8.9 | 9.5 | n/a | **Fail: no data access** |
| FinanceInsights | 6 | **0** | 0 | 6 (no data) | 108.2 | 159.1 | n/a | **Fail: no data returned** |
| ProductBrief | 4 | 4 | 0 | 0 | 62.1 | not enough data | 62.1 | Pass |
| ProductBriefFootball | 3 | 3 | 0 | 0 | 59.8 | not enough data | 59.8 | Pass |
| Chitchat (incl. definitions) | 8 | 8 | 0 | 0 | 11.4 | 13.2 | 11.4 | Pass |
| Multi-Domain | 1 | 1 | 0 | 0 | 49.8 | not enough data | 49.8 | Pass (both parts answered) |
| **Total** | **43** | **31 (72.1%)** | **2 (4.7%)** | **10 (23.3%)** | | | | **Gate not met** |

\* With 5 or 6 samples, p95 is the slowest single turn. p95 is not shown for fewer than 5
samples. The AI.Vision p95 is Q01's re-run (172.5 s). Its other four questions took 45 to
69 s.

| Rate (43 turns) | Value |
|---|---:|
| Completed outcomes (`FULL_ANSWER` + `VALID_DIRECT_RESPONSE`) | **72.1%** (16 + 15) |
| Full data answers | 37.2% (16) |
| Valid direct responses | 34.9% (15) |
| Clarifications | 4.7% (2) |
| Refusals and errors (routing refusal 0, access error 4, no data 6) | 23.3% (10) |
| Partial answers | 0% |
| HTTP errors and timeouts (result of record) | 0% |
| Analytical questions only (27) | 15 of 27 full answers (55.6%) |
| Analytical, accessible domains only (AI.Vision, ShareOfSearch, RangeInsights; 16) | **15 of 16 (93.8%)** |

**Latency by kind (completed turns).** Chitchat and definitions took 10 to 13 s. Product
briefs took 58 to 69 s. Data answers took 31 to 51 s, except the AI.Vision outliers of
68.5 s and 172.5 s. Clarifications and access errors returned in 7 to 10 s. FinanceInsights
took 94 to 159 s to report that it had no data.

## 5. Questions unavailable to the current user

| Questions | Evidence | Assessment |
|---|---|---|
| Q18, Q19, Q20, Q21 (ProductReviews) | `action: error`: *"You don't have access to the 'ProductReviews' data source. Contact your workspace admin to request access. (Reference: …)"* | **Access denied for this user.** It comes back as HTTP 200 with an in-band error, not as a 403. This is relevant to the 403 tracker: a data-permission failure does not appear as a 403 anywhere a client can see. |
| Q17 (ProductReviews) | Clarifying question | Would probably hit the same access error once clarified. Not tested further. |
| Q22 to Q27 (FinanceInsights) | SQL ran and returned zero records. The answers say the data is not loaded, the filters do not match, or (for Q25) *"access permissions may be restricted"*. | **Cause not determined.** Possibly row-level access for this user, possibly unloaded or empty data marts. One account cannot tell these apart. Needs the data owner, or a second user with confirmed Finance access. |

## 6. Test-harness incident: laptop standby (not a BFF fault)

On the first attempt, five turns failed with a `requests` `ConnectionError` and no HTTP
status: Q01 after 215.2 s, Q05 after 121.4 s, Q26 after 89.1 s, and Q27 and Q37 after 0.0 s.

* **Correlation.** The Windows System log (Kernel-Power 506/507/172) shows the laptop
  entering Modern Standby with its network disconnected at exactly those times. Each failure
  happened at, or in the second after, a wake. Two "5 s" pauses actually lasted 2 and 6
  minutes. See
  [`failure-evidence/standby-correlation.json`](../results/bff-valid-question-retest/20260924-115127/failure-evidence/standby-correlation.json).
* **Server side.** Q01, Q05 and Q26 were **completed and saved by the BFF** as `summarized`
  turns, but the laptop was asleep and never received them. Q27 and Q37 never reached the
  server.
* **Re-run.** Each of the five was run once more. All were delivered: Q01 and Q05 as full
  answers, Q26 and Q27 as "no data", and Q37 as a valid direct response.
* **Impact on figures.** No completed turn overlaps a disconnected window, so screening
  latencies are unaffected.
* **Prevention.** The test scripts now call `SetThreadExecutionState` to keep the machine
  awake while they run. This applies only to the running process and changes no power
  settings. A closed lid or a manual sleep still overrides it.

| View | Completed | Rate |
|---|---:|---:|
| As run, automatic classification only | 30 of 43 | 69.8% |
| As run, after manual review (standby failures counted as failures) | 28 of 43 | 65.1% |
| **Result of record** (standby turns re-run, reviewed) | **31 of 43** | **72.1%** |

The gate is missed in every view.

## 7. Consistency

**Repeat run.**
* One user, 13:26:53 to 13:42:57 UTC, after the recovery stage.
* One question from each accessible analytical domain, plus the multi-domain question.
* 5 rounds, run as interleaved passes (Q02, Q06, Q12, Q43, then again), each in a new
  session with a 5 s pause.
* The outcome classification and whether each requested subject was addressed are
  compared. The wording is not.
* Evidence: [`consistency/`](../results/bff-valid-question-retest/20260924-115127/consistency/).

| Question | Domain | Attempts | Full answers | Clarifications | Refusals / errors | Consistency | Classification changed? | Latency range (s) | Subjects addressed |
|---|---|---:|---:|---:|---:|---:|---|---|---|
| Q02 | AI.Vision | 5 | 5 | 0 | 0 | **100%** | No (`summarized` every time, 5 rows) | 47.7 to 51.0 | Top-5 purchase consideration, 5/5 |
| Q06 | ShareOfSearch | 5 | 5 | 0 | 0 | **100%** | No (3 rows) | 34.9 to 36.2 | Share of search for 3 brands, 5/5 |
| Q12 | RangeInsights | 5 | 5 | 0 | 0 | **100%** | No (1 row) | 32.4 to 39.2 | Training KCC SS27 article count, 5/5 |
| Q43 | Multi-Domain | 5 | 5 | 0 | 0 | **100%** | No (3 rows) | 41.4 to 60.5 | MBV **and** share-of-search rank, 5/5 |
| **Total** | | **20** | **20** | 0 | 0 | **100%** | | 32.4 to 60.5 | |

Across all repeated questions (Phase 1, all Phase 2 stages and this run), **no question
changed classification.** Every analytical question in the workload returned a full
answer every time it was asked: 51 load turns plus 20 consistency turns. This differs
from the generic-question test, where one question was sometimes refused and sometimes
answered.

**Content note (not a classification change).** Q43's masked answers show that the
*scope* of its figures varied between attempts:
* In 4 of 5 attempts the MBV was stated for Germany, and in 1 of 5 for the Europe market.
* Once, the share-of-search rank had a different number of digits. The answers used
  different aggregations: an average across all periods, or the latest period.

The data owners should look at this. It is a reproducibility risk for multi-domain
answers, not a routing failure.

Before this run, the five standby re-runs were the only repeats (§6). Their server-side
outcomes also matched: Q01 and Q05 were `summarized` with data both times, and Q26 was
"no data" both times.

## 8. Isolation and contract

* **Session echo.** 43 of 43 turns that received a response (38 first attempts and 5 re-runs) returned the request's `session_id`.
* **History readback.** 43 of 43 readbacks through `GET /api/session-chat` showed exactly one
  record, containing that question. There were 0 mismatches.
* **Contract.** No `INVALID_CONTRACT` responses and no 401, 403, 429 or 5xx.
* **Old check.** The original scenario's check (HTTP 200 plus a known `action`) would have
  passed **12 turns that are not completed**: 2 clarifications, 4 access errors and 6
  no-data answers.

## 9. Workload used in Phase 2 (approved and executed)

The workload was built from the result of record: only the 31 completed questions. The
file is
[`workload/phase2-workload.json`](../results/bff-valid-question-retest/20260924-115127/workload/phase2-workload.json).

| Group | Questions | Notes |
|---|---|---|
| `analytical-heavy` | Q01–Q05, Q06–Q10, Q11–Q14, Q16 (15) | Every completed data-backed answer: AI.Vision, ShareOfSearch and RangeInsights |
| `generative` | Q28 to Q34 (7) | Product briefs. Q31 is in the group, but the 30-turn cycle holds 6 brief slots, so it was never asked. |
| `lightweight` | Q35 to Q42 (8) | Chitchat and definitions |
| `multi-domain` | Q43 | Run separately, in the consistency run (§7) |
| **Excluded (12)** | ProductReviews Q17–Q21 (access-coverage limitation); FinanceInsights Q22–Q27 (data availability or permission requires investigation); RangeInsights Q15 (clarification) | **Not used, and not counted as successes or in any capacity figure.** Their Phase 1 results stay in §3. |

* **Planned mix.** A fixed 30-turn cycle built from the block `A A A G A A A G A L`: 21
  analytical (70%), 6 generative (20%) and 3 lightweight (10%). One cycle is shared by all
  virtual users, and each stage starts at the top of it.
* **Scenario.**
  [`scenarios/approved_question_scenario.py`](../scenarios/approved_question_scenario.py)
  with [`config/locust.deployed-approved.conf`](../config/locust.deployed-approved.conf).
  Each journey is `POST /api/chat` in a new test-owned session, followed by a
  `GET /api/session-chat` readback.

**Distribution actually executed:**

| Stage | Analytical | Generative | Lightweight | Total turns |
|---|---:|---:|---:|---:|
| P2-1 (1 user) | 3 (75%) | 1 (25%) | 0 | 4 |
| P2-2 (5 users) | 21 (72%) | 6 (21%) | 2 (7%) | 29 |
| P2-3 (10 users) | 24 (71%) | 7 (21%) | 3 (9%) | 34 |
| P2-4 (recovery) | 3 (75%) | 1 (25%) | 0 | 4 |
| **All load stages** | **51 (71.8%)** | **15 (21.1%)** | **5 (7.0%)** | **71** |

The 1-user stages are 3 minutes long, so they only reach the first 4 turns of the cycle
(Q01, Q06, Q11, Q28). Baseline and recovery therefore asked exactly the same questions,
which makes them directly comparable. **Analytical results are reported separately from
direct responses** throughout (§12).

## 10. Stop conditions and safety

* **Guard.** An audit guard checked every 30 s. It would stop the run on any of:
  * a transport failure rate above 5%;
  * 3 or more 401 or 403 responses in one window;
  * sustained 429 or 5xx responses;
  * completed-answer p95 above 3 × the one-user warm baseline for two consecutive windows
    (baseline 65.1 s, from P2-1, so the limit was 195.3 s);
  * load-generator CPU above 95%;
  * any session echo or history mismatch.
* **No stage was stopped.** One 30 s window in P2-3 reached 197.4 s: a single slow
  AI.Vision turn, with only 2 completions in that window. The next window was 135.6 s, so
  the breach was not sustained.
* **Environment.** The Databricks OAuth U2M token was checked before Phase 2 (SCIM `Me`
  200, `/api/healthz` 200 `obo`, `app_env: dev`) and refreshed by the stage runner as
  needed. The laptop was kept awake with `SetThreadExecutionState`. There were no
  standby events or connection errors in Phase 2.
* **Load ceiling.** At most 10 concurrent users.

## 11. Decision record

* **Gate.** Phase 1 missed the 80% gate at 72.1%. Load testing was held and the screening
  results were shown.
* **Requester's decision (24 Sep 2026):** remove the overall gate. Load-test only the 31
  completed questions. Report ProductReviews as an access-coverage limitation, and
  FinanceInsights as "data availability or permission requires investigation". Exclude
  the clarification questions. Run 1, 5 and 10 users, then 1-user recovery and the
  consistency check.

## 12. Phase 2 results (accessible and usable domains only)

Evidence: `stages/P2-*/` (Locust HTML and CSV, `requests.jsonl`, `summary.json`,
`guard.json`, `usage.jsonl`, `manifest.json`) and `final-summary.json`.
* **Latency** is client-measured `POST /api/chat` time to the complete JSON response.
* **p95 and p99** equal the maximum when a group has fewer than 20 samples.
* **"Full answer"** means a `FULL_ANSWER` data answer. In Phase 2 every full answer came
  from an analytical domain, so "full answer" and "analytical" are the same numbers.

| Stage (UTC) | Users (configured / peak) | Spawn | Duration | Sessions | Sessions/s | Requests | RPS | Chat turns | Completed | Clarifications | Failures | HTTP failure rate |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| P2-1 baseline, 13:06:44 to 13:10:07 | 1 / 1 | 1/s | 3 min (203 s wall) | 4 | 0.020 | 8 | 0.040 | 4 | 4 (100%) | 0 | 0 | 0% |
| P2-2 load, 13:10:29 to 13:16:29 | 5 / 5 | 1/s | 5 min (360 s) | 29 | 0.081 | 58 | 0.161 | 29 | 29 (100%) | 0 | 0 | 0% |
| P2-3 stress, 13:16:39 to 13:23:14 | 10 / 10 | 1/s | 5 min (395 s) | 34 | 0.086 | 68 | 0.173 | 34 | 34 (100%) | 0 | 0 | 0% |
| P2-4 recovery, 13:23:27 to 13:26:44 | 1 / 1 | 1/s | 3 min (197 s) | 4 | 0.020 | 8 | 0.041 | 4 | 4 (100%) | 0 | 0 | 0% |

**Full answers (analytical data answers):**

| Stage | n | p50 | p90 | p95 | p99 | Range | Full answers/min |
|---|---:|---:|---:|---:|---:|---|---:|
| P2-1, 1 user | 3 | 47.4 s | 47.8 s | 47.8 s | 47.8 s | 35.9 to 47.8 s | 0.89 |
| P2-2, 5 users | 21 | **51.7 s** | 74.1 s | **84.3 s** | 147.4 s | 31.6 to 147.4 s | **3.51** |
| P2-3, 10 users | 24 | **95.9 s** | 129.4 s | **135.6 s** | 197.4 s | 42.3 to 197.4 s | **3.66** |
| P2-4, recovery | 3 | 43.9 s | 48.6 s | 48.6 s | 48.6 s | 36.6 to 48.6 s | 0.92 |
| One-user reference (Phase 1 + P2-1 analytical) | 18 | 41.7 s | 68.5 s | 172.5 s\* | | 31.4 to 172.5 s | |
| Consistency run, 1 user (Q02, Q06, Q12) | 15 | 37.2 s | 50.0 s | 51.0 s | | 32.4 to 51.0 s | |

\* A single AI.Vision outlier (the Q01 re-run in Phase 1). Load is therefore compared with
the one-user reference on **p50 and p90**:
* 5 users: **×1.24 and ×1.08**.
* 10 users: **×2.30 and ×1.89**.

**Direct responses, reported separately:**

| Stage | Briefs: n, p50, max | Chitchat and definitions: n, p50, max | Completed journeys/min (all kinds) |
|---|---|---|---:|
| P2-1, 1 user | 1, 65.1 s | none | 1.19 |
| P2-2, 5 users | 6, 64.2 s, 66.7 s | 2, 9.4 s, 17.0 s | 4.85 |
| P2-3, 10 users | 7, **112.7 s**, 125.5 s | 3, **88.1 s**, 91.4 s | 5.18 |
| P2-4, recovery | 1, 61.1 s | none | 1.22 |

**Full answers by domain (p50 / max):**

| Domain | 5 users | 10 users |
|---|---|---|
| AI.Vision | n 7: 63.1 / 147.4 s | n 8: 110.6 / 197.4 s |
| ShareOfSearch | n 7: 39.7 / 70.8 s | n 8: 83.6 / 135.6 s |
| RangeInsights | n 7: 51.7 / 66.6 s | n 8: 89.7 / 128.5 s |

**Other measures, all stages:**
* **Errors and timeouts.** 0 timeouts. 0 responses with status 401, 403, 429 or 5xx. 0
  refusals, errors, empty answers or clarifications. 0 follow-up suggestions mistaken
  for answers.
* **Isolation.** 0 session echo mismatches. 71 of 71 history readbacks were isolated.
  `/api/session-chat` p50 was 0.2 s at every level, with a maximum of 0.51 s.
* **Load generator.** CPU at most 38.8%. The Locust process used at most 0.9% CPU and
  63.7 MB of memory. At least 12.3 GB of memory stayed free.

**Interpretation:**
* **Last stable tested level: 5 users.**
  * Every turn completed.
  * Full-answer p50 rose only 1.24 × (p90 × 1.08).
  * Full-answer throughput went up about 4 × from 1 user (0.89 to 3.51 per minute).
* **First degraded level: 10 users.**
  * Every turn still completed, with no errors.
  * Full-answer p50 was 2.3 × the one-user reference.
  * Throughput stayed **flat**: 3.51 to 3.66 full answers per minute, and 4.85 to 5.18
    completed per minute.
  * Fast replies queued. Chitchat went from about 10 s to 88 s, and briefs from 64 s to
    113 s.
* **Queueing.** Extra users turned into waiting time, not throughput. Little's law gives
  about 4 turns in service at once: 0.086 completed per second × about 49 s mean one-user
  service time ≈ 4.2. This matches the earlier serving-endpoint finding that a single
  Small entity processes about 4 requests at a time. **Confirmed on 25 Sep by the serving
  traces (§14).**
* **Recovery: full.** The same four questions as the baseline gave a full-answer p50 of
  43.9 s (baseline 47.4 s), a brief in 61.1 s (baseline 65.1 s), and 100% completed.

## 13. Comparison with the original generic-question test

| Measure | Original generic-question test | Approved-question retest | Change |
|---|---:|---:|---:|
| Questions/turns | 73 BFF chat turns from 5 generic questions (A2 to R1b) | 43 questions screened; 71 load turns and 20 consistency turns on the 31 usable ones | Different design |
| Completed answer rate | 45% `summarized` (33/73); 32.9% (24/73) had data rows | Screening: 72.1% (31/43). Load: **100% (71/71)** | Up |
| Clarification rate | 38% (28/73) | Screening: 4.7% (2/43). Load: 0% | Down |
| Refusal/error rate | 16% (12/73) routing refusals | Screening: 23.3% (10/43), all from access or data problems, 0 routing refusals. Load: 0% | Different cause |
| 1-user full-answer p50/p95 | 84.5 / 86.1 s (n = 2: A2, A3) | 47.4 / 47.8 s (n = 3). Reference: 41.7 / 172.5 s (n = 18) | Faster |
| 5-user full-answer p50/p95 | 71.4 / 81.8 s (A4, n = 3) | 51.7 / 84.3 s (n = 21) | Similar p95 |
| 10-user full-answer p50/p95 | 113.3 / 195.8 s (E1, n = 17) | 95.9 / 135.6 s (n = 24) | Lower |
| Full answers per minute (5 / 10 users) | 0.80 / 2.78 | 3.51 / 3.66 | Up (mix effect) |
| Last stable load | 5 users (all chat turns) | **5 users (full answers)** | Unchanged |
| First degraded load | 10 users | **10 users** | Unchanged |

* **Earlier samples were thin.** The earlier full-answer figures come from 2 to 17
  samples of a different question mix, so the latency changes show direction only.
* **The original finding stands.** Generic questions produced 54% clarifications and
  refusals. The approved questions show that the capacity picture holds for real business
  questions in the accessible domains.

## 14. Root cause confirmed by serving traces

The traces come from the MLflow serving-trace experiment `Orchestrator_Serving_Traces`: 91
of them are the test's requests, joined on session ID. Arrival times come from the
endpoint's inference table.

| Users | Endpoint total (median) | Wait before the agent started | Agent run | LLM | Agent runs at once (max / avg) |
|---:|---:|---:|---:|---:|---|
| 1 | 45.6 s | 0.0 s | 45.5 s | 17.9 s | 1 / 0.95 |
| 5 | 55.3 s | 3.8 s | 46.7 s | 18.0 s | 5 / 3.91 |
| 10 | 96.5 s | **55.6 s** | 43.6 s | 17.7 s | **5 / 4.23** |

* **Downstream services and CPU stayed the same from 1 to 10 users:**
  * Genie, including its SQL: 17 to 25 s against 17 to 21 s.
  * The AI.Vision endpoint: 28.0 s against 28.2 s.
  * A single LLM call: 3.1 s against 3.0 s.
  * In-process CPU time: about 0.1 s.
* **At 10 users, chitchat waited 78 s** for about 9 s of work.
* **Root cause: the serving entity's Small scale-out, which allows 4 concurrent requests.**
  Recommended fix: move to Medium (8–16), then re-test at 10 users.
* **Detail:** main report §0.13 and
  [`serving-traces/SUMMARY.md`](../results/bff-valid-question-retest/20260924-115127/serving-traces/SUMMARY.md).

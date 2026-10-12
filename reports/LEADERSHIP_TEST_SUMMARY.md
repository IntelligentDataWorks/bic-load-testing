# IRIS (BIC) Performance and Reliability Test: Leadership Summary

**Date:** 24 September 2026. **Environment:** development only (not production).
**Updated** after a second test that used 43 approved business questions.

**Outcome: Ready with conditions.** For the business areas this test account can use,
IRIS answered every approved question it was asked under load. It stays reliable with up
to about **5 people asking at the same moment**. At **10** it still answers everything, but
data answers take about twice as long. **Two business areas returned nothing usable** for
this account.

---

## Latest result: approved business questions

### Were the approved business questions answered?

We tried all **43 approved questions**, one at a time. **31 (72%) produced a complete
answer.** The other 12 were not load-tested:

| Area | Result | Why |
|---|---|---|
| Brand health (AI.Vision), search share, range and merchandising | 15 of 16 answered with data | One question got a follow-up question instead of an answer |
| Product briefs, greetings and definitions | 15 of 15 answered | |
| Question spanning two areas | Answered in full | |
| **Product reviews** | **0 of 5** | **The test account has no access** to this data. This limits test coverage; it is not a performance failure. |
| **Finance (net sales, backlog, business on hand)** | **0 of 6** | **No usable data came back.** Missing data or a permission issue: **needs investigation**. |

The 12 questions left out of the load test include both questions that got a follow-up
question instead of an answer: one in range and one in product reviews.

### Did the core journey stay reliable under load?

**Yes, for the areas that work.** Across the 1-, 5- and 10-person tests, **all 71 questions
got a complete answer**, with no errors, no rejected requests and no mixing of
conversations. When we asked the same four questions five times each, the result was the
same every time (100%). The earlier problem of a question being answered once and turned
down the next time did **not** happen with the approved questions.

### How much load it handled

| People asking at the same time | Typical wait for a data answer | Slowest 1 in 20 | Quick replies (greetings) | Assessment |
|---|---|---|---|---|
| 1 | About 45 seconds | About 50 seconds | About 10 seconds | Normal |
| **5** | **About 50 seconds** | About 85 seconds | About 10 seconds | **Highest stable level tested** |
| **10** | **About 95 seconds** (about double) | About 2¼ minutes | About 90 seconds | **Performance degraded here** |

* IRIS produced about **3.5 data answers per minute** at most. Going from 5 to 10 people
  did not raise that number, so people simply waited longer. Even a simple "hi" waited in
  the queue behind data questions.
* Once the load was removed, response times went straight back to normal.
* Data answers are reported apart from quick replies, so the quick replies do not make
  the waits look shorter than they are.

### Comparison with the first test

| Measure | First test (generic questions) | Retest (approved questions) |
|---|---|---|
| Questions asked | 73, from 5 generic questions | 43 screened; 91 asked in the load and repeat tests |
| Complete answers | 45% | 72% of all 43 questions; **100%** of those load-tested |
| Follow-up questions instead of answers | 38% | 5% (none under load) |
| Turned down or failed | 16% (could not tell which data was meant) | 23%, all from product-review access and missing finance data; none under load |
| Typical data answer: 1 / 5 / 10 people | About 85 s / 70 s / 115 s (few samples) | About 45 s / 50 s / 95 s |
| Highest stable level | 5 people | **5 people** (confirmed) |
| Where it slows down | 10 people | **10 people** (confirmed) |

## Why it slows down (confirmed)

We traced every question inside the AI answering engine, step by step.

* **At 10 people, each question waited about 55 seconds before any work on it began.**
  The work itself took the same time as with 1 person, about 45 seconds.
* **The services the engine relies on did not slow down.** The AI language model, the
  data services (Genie) and the brand-survey service were as fast at 10 people as at 1.
  The engine's processor was not busy either.
* **The cause is a setting.** The engine is set to its smallest size, which works on only
  **4 questions at a time**. A simple "hi" waited 78 seconds for its turn.
* **Fix:** raise the engine's setting from Small (4 at a time) to Medium (8 to 16 at a
  time), then repeat the 10-person test to confirm the waits disappear.

We also found that **the engine's model version was changed three times during testing on
24 September.** The retest ran entirely on one version, so its results are directly
comparable.

## Business risks

1. **Coverage gaps.** Product reviews and finance gave no usable answers for this
   account. If real users see the same, two of seven business areas are unavailable to
   them. The access error comes back as an ordinary reply, not as an "access denied"
   error, so it is easy to miss.
2. **Capacity.** More than about 5 people asking at the same moment roughly doubles the
   wait. Nothing fails, but the experience suffers.
3. **Answer consistency.** Question types are now stable. One cross-area question gave
   slightly different figures from one run to the next (market scope and ranking), which
   needs review by the data owners.
4. **Finance "no data" replies are slow.** Each took 1.5 to 2.5 minutes to say that no
   data was available.

## Identity limitation

**Every simulated person used one real account**, and that account has administrator-level
access to the AI engine. The results show that many simultaneous conversations work for
one person. They do not show how different people are kept apart, or how users with
restricted access are treated. **No claim is made about how product reviews or finance
would perform at scale.**

## Readiness decision

**Ready with conditions:**
* **For:** continued development use and pilots with no more than about **5 people
  actively asking at the same time**.
* **Scope:** limited to brand health, search share, range and merchandising, product
  briefs, and general questions.
* **Not ready:** product reviews and finance, until access and data are resolved.
* **Not yet shown:** 10 or more simultaneous active users without longer waits.

## Top three recommended actions

1. **Fix product-review access and finance data.** Grant or confirm access, find out why
   finance returns no records, then re-test those 11 questions.
2. **Raise the AI answering engine from Small to Medium.** It is confirmed to handle only
   4 questions at a time. Then repeat the test at 10 and 20 people.
3. **Test with more than one account.** Use two restricted test accounts to confirm
   access rules and separation between users.

Full detail: [FINAL_LOAD_STRESS_TEST_REPORT.md](FINAL_LOAD_STRESS_TEST_REPORT.md) (section 0)
and [BFF_APPROVED_QUESTION_VALIDATION.md](BFF_APPROVED_QUESTION_VALIDATION.md).

---

# First test (generic questions), for comparison

The summary below is from the first round of testing earlier the same day. It is kept
as it was. Where it differs from the section above, the section above is the current
view of the back-end service. The web application, the AI engine and the access-error
findings below were not re-tested and still stand.

**Date:** 24 September 2026. **Environment:** development only (not production).
**Outcome: Ready with conditions.** IRIS works reliably for up to about **5 people
asking questions at the same moment**. At **10 at the same moment** it stays
reliable, but answers take about twice as long.

---

### What we tested

We tested IRIS the way a user reaches it:
* through the web application
* through the application's back-end service
* through the AI answering engine directly

We tested each path with 1, 5 and then 10 simulated people asking questions
continuously, for 3 to 5 minutes at each level. We also ran real browser sessions
(someone opening IRIS, starting a conversation, asking a business question and
reading the answer) on their own and while the system was busy. Finally, we checked
how IRIS handles missing, invalid or expired sign-in details.

### What worked

* **Nothing failed.** In about 700 requests we saw no errors, no rejected requests
  and no outages. That total includes about 165 business questions answered by the
  AI engine and 9 complete browser sessions.
* **Every browser session succeeded.** Each time, a user could sign in, ask a
  question and see a complete answer on screen, including while the system was
  under load.
* **Conversations stayed separate.** No answer or history appeared in the wrong
  conversation.
* **Access control behaved correctly.** Missing or invalid sign-in details were
  refused cleanly, and never with a confusing "access denied" (403) error.
* **The system recovered fully.** Once the load was removed, response times went
  back to normal straight away.

### How much load it handled

| People asking at the same time | Typical wait for a full data answer | Errors | Assessment |
|---|---|---|---|
| 1 | About 35 seconds (direct), up to about 85 seconds for complex questions | None | Normal |
| **5** | About 40 seconds (a little slower). One in 20 answers took over a minute. | None | **Highest stable level tested** |
| **10** | About 75 seconds (about double). Complex questions took up to about 3 minutes. Quick replies slowed from about 8 seconds to about 50. | None | **Performance degraded here** |

* The AI engine completed **about 6 full answers per minute at most**. Going from 5
  to 10 people did not increase that number. People simply waited longer.
* A user who asked a question while 5 others were waiting on complex answers saw
  **nothing for about 30 seconds** (normally about 4) before the answer began to
  appear. The answer did arrive.
* These figures come from a short test with a single test account. They are not a
  guarantee of how many users IRIS supports.

### Likely cause of the slowdown (now confirmed: see "Why it slows down" above)

The AI answering engine currently runs on **one small computing unit that handles
all traffic**. The numbers match a unit that can work on about four questions at a
time. The web application and the back-end service stayed fast throughout, and the
test laptop was not a limiting factor. The engine's own monitoring data needs to be
checked to confirm this.

### Material risks

1. **Capacity:** more than about 5 people asking at the same moment will make
   waiting times noticeably longer. There is no failure, but the experience is poor.
2. **Answer quality:** with the generic test questions, **about 1 in 6 questions
   was turned down** ("I could not tell which data this question is about"), and
   **about 4 in 10 got a follow-up question** instead of an answer. The same
   question was sometimes answered and sometimes turned down.
3. **Test coverage:** all testing used one test account with high privileges.
   Problems that affect only some users, or users with limited access, could not be
   tested. Several open items in the access-error tracker fall into this group.
4. **Longer use was not tested.** Sign-in tokens expire after 60 minutes, and no
   test ran longer than about 7 minutes.

### Access-error (403) conclusion

No "access denied" (403) error appeared in any test. Every sign-in problem we
could safely create was handled correctly, and each part of the system responds
in a recognisably different way, which will make future incidents quicker to
diagnose.

The fix from the tracker that adds the Genie data permission is **confirmed as in
place**. The items affecting only certain users, specific permission errors, and
permissions being reset after a deployment **could not be verified**. Doing so
would need extra test accounts or configuration changes, which were outside the
agreed scope.

### Identity-testing limitation

All simulated people shared **one real account**, and that account has
administrator-level access to the AI engine. The results show that many
simultaneous conversations work for one person. They do **not** show that
different people are kept apart, or how users with restricted access are treated.

### Readiness recommendation

**Ready with conditions.** Suitable for continued development use and for pilots
where **no more than about 5 people are actively asking questions at the same
time**. Not yet shown to be ready for 10 or more simultaneous active users without
longer waits.

### Top three next actions

1. **Add capacity to the AI answering engine**, or confirm its actual limit, then
   repeat the test at 10 and 20 simultaneous users.
2. **Create two restricted test accounts** and repeat the access tests, to close
   the tracker items that affect only certain users.
3. **Improve answer consistency and the test questions.** Look into why the same
   question is sometimes turned down, and base future tests on real business
   questions so the results reflect actual use.

The full technical detail is in
[FINAL_LOAD_STRESS_TEST_REPORT.md](FINAL_LOAD_STRESS_TEST_REPORT.md). The
access-error analysis is in [403_TEST_MATRIX.md](403_TEST_MATRIX.md).

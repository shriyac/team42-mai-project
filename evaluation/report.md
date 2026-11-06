# LAGA MVP evaluation report

## Phase 9B execution review — 2026-11-06

Both modes below use the current Q01–Q10 dataset fingerprint. LIVE used an
explicit in-memory synthetic-demo configuration and the production retriever;
the application's live/demo flags remained disabled. Required API Secrets were
present and differed from the previously exposed values; no credential values
or reusable hashes were emitted.

### Explicit rubric-based answer review

Review criteria: cover the requested question parts; state the annotated facts;
use authorized, exact canonical evidence; do not invent missing facts; deny
foreign-lease access before retrieval. These are agent-authored evidence reviews,
not production-model self-scores or independent human/legal review.

- **LIVE Q01–Q04:** Returned answers contain the requested date, operative pet
  permission, selected late-fee conditions, and end-date/deposit-deduction terms.
  Exact citations and required-source assertions passed.
- **LIVE Q05 — failure:** The answer repeats annexure A 8.1 for both question
  parts. This does acknowledge pet-damage responsibility, but does not explain
  the documented-damage/beyond-ordinary-wear condition or cite deposit record
  4.2. It is partially supported, not an invented answer, but fails the annotated
  completeness rubric. No production change was made to improve this score.
- **OFFLINE Q02 — reference-coverage limitation:** The returned section 11
  passage supports the pet-permission facts, but the annotation selects annexure
  A 8.1. Its failure is selected-source coverage, not evidence of hallucination.
  The strict composite factual-support score includes this coverage requirement.
- **OFFLINE Q03–Q05:** The section-based fixture omits the operative late-fee
  evidence for Q03 and the annexure/deposit-damage passages needed by Q04/Q05.
  Q03 abstains; Q04 lacks the deduction facts; Q05 repeats permission without
  damage consequences. These are fixture/routing diagnostics, not Pinecone scores.
- **Both modes Q06–Q09:** Clarification/abstention with no invented calculation
  or credential citations passed. The Q06 numerical reference is conditional;
  neither fee question invoked the calculator. Calculation exact-match therefore
  remains **NOT_MEASURED (denominator 0)**, not 100%.
- **Both modes Q10:** The actual `BackendAPI.post_assistant_messages()` call
  denied Maya's `lease-2` request with 404 before any retrieval or calculator.

### Regression verification

- Focused evaluation/dataset tests: **27 passed**.
- Full isolated Python regression suite: **333 passed + 57 subtests**, one
  dependency deprecation warning.
- Frontend tests: **46 passed**.
- API-mode frontend production build: **passed**.
- Public report/results checked for effective API-key values: none found.
- No production agent, prompt, retrieval algorithm, backend/authentication,
  calculator or frontend changes; no Pinecone writes, commits, pushes or merges.

## Method and limitations

All assertions are deterministic automated checks; no LLM judge or confidence score is used.
Golden reference assertions were agent-authored from the synthetic unsigned PDF; unknown references must be marked
needs_annotation. No independent legal or end-to-end human answer-quality review was performed.
Mock retrieval uses transparent topic rules, NOT Pinecone or embeddings; its scores are fixture diagnostics,
not live RAG performance. The authorization denial uses real backend ownership methods against a disposable
SQLite fixture in mock mode, not an authenticated browser/session test.
An OFFLINE run does not activate retrieval or constitute a new LIVE evaluation.
Recall@5 and Precision@5 use the first five unique chunks in first-seen subquestion/retry order.
Scores are macro-averaged over executed cases with nonempty reference chunk annotations; Precision@5 always
divides by five, including empty slots. Reference sets are selected, not exhaustive: precision is provisional
against those annotations. Repeated retries are captured but are not counted as independent questions.
Citation correctness compares source metadata, scope, references and literal quotes against returned evidence.
Groundedness is structural excerpt support only, NOT semantic entailment or legal correctness; fee arithmetic
is checked separately with Decimal. Clarification requires abstention with no citations or calculation.
Factual support uses an explicit rubric: required annotated answer fragments, canonical citation provenance,
and required-source coverage. This is automated evidence-based review, not model confidence or an independent
human semantic/legal assessment. Legitimate alternative passages can fail selected-chunk coverage.
Answer references use stated substring assertions, not full natural-language equivalence.
Latency includes per-case authorization, graph compilation, retrieval/retries and tools; excludes corpus
preparation and global live preflight. No live provider latency is claimed for mock runs.
Disabled/unverified live runs are NOT_RUN / BLOCKED, never PASSED. Missing-annotation cases are NOT_RUN.
An explicit isolated-demo run uses an in-memory configuration only; application flags stay unchanged.
The public response status comes from the existing backend adapter and schema; Q10 calls the actual
BackendAPI.post_assistant_messages method, but this is not an authenticated HTTP/browser test.
Q06/Q07 currently require clarification; their conditional reference is not a mandatory calculator call.
Calculation exact-match is NOT_MEASURED when no case expects a numeric calculation.
No snapshot/binding approval, re-ingestion, persistent flag changes, or application code rewrites are performed.

## OFFLINE evaluation

Generated (UTC): 2026-11-06T16:34:17.802740+00:00

Questions executed: **10/10**. Passed: **6**; failed: **4**; not run: **0**; blocked: **0** (subset of not run).

| Metric | Result | Denominator |
|---|---:|---:|
| tool_selection_accuracy | 1.0000 (10/10) | 10 |
| calculation_exact_match | NOT_MEASURED (0/0) | 0 |
| citation_correctness | 0.8000 (4/5) | 5 |
| groundedness_structural | 0.8000 (4/5) | 5 |
| returned_citation_correctness | 1.0000 (4/4) | 4 |
| answer_factual_support_rubric | 0.2000 (1/5) | 5 |
| abstention_clarification_correctness | 1.0000 (4/4) | 4 |
| authorization_correctness | 1.0000 (1/1) | 1 |
| recall_at_5 | 0.3571 | 7 |
| precision_at_5 | 0.1143 | 7 |
| overall_case_pass_rate | 0.6000 (6/10) | 10 |
| latency_seconds | average 0.051504s; median 0.013690s | 10 |

Cases with no ground-truth chunks: Recall@5 is **NOT_MEASURED**, not zero or a guessed score. Citation correctness includes expected answer/calculation cases with missing citations as failures. Returned-citation correctness scores only cases that actually returned citations.


### Per-question outcomes and failure examples

- `Q01` — **PASSED**: Assertions passed.
  - Response status: `supported`; latency: 0.400944s; tools: retrieval.
- `Q02` — **FAILED**: reference_evidence_coverage, factual_support
  - Response status: `supported`; latency: 0.013890s; tools: retrieval.
  - Actual answer: For “Are pets allowed under my lease?”, the lease evidence states "☑ - Pets are Allowed. Prior written approval required. Number of Pets: 1 Types: Approved cat Miso, domestic shorthair, 11 lb (2026-01-25). Maximum Weight (per pet): 50 Pounds One-time pet fee: $250.00, nonrefundable; monthly pet rent: $0.00." [S1].
- `Q03` — **FAILED**: citations, groundedness, answer_reference, reference_evidence_coverage, factual_support, behavior, response_status
  - Response status: `needs_clarification`; latency: 0.014228s; tools: retrieval.
  - Actual answer: I can’t answer from the authorized lease evidence available. Please provide the missing lease clause or clarify the question.
  - Validation errors: No authorized evidence was retrieved.
- `Q04` — **FAILED**: answer_reference, reference_evidence_coverage, factual_support
  - Response status: `supported`; latency: 0.012885s; tools: retrieval.
  - Actual answer: For “When does my lease end”, the lease evidence states "Start Date: 2026-02-01 End Date: 2027-01-31 (inclusive; 12 calendar months)" [S1].  For “what happens to my security deposit?”, the lease evidence states "☑ - Security Deposit. Due at commencement; no payment recorded. Amount: $2,200.00 ● Returning to Tenant: _____ days after lease termination." [S2].
- `Q05` — **FAILED**: answer_reference, reference_evidence_coverage, factual_support
  - Response status: `supported`; latency: 0.012968s; tools: retrieval.
  - Actual answer: For “Are pets allowed”, the lease evidence states "☑ - Pets are Allowed. Prior written approval required. Number of Pets: 1 Types: Approved cat Miso, domestic shorthair, 11 lb (2026-01-25). Maximum Weight (per pet): 50 Pounds One-time pet fee: $250.00, nonrefundable; monthly pet rent: $0.00." [S1].  For “what happens if my pet damages the apartment?”, the lease evidence states "☑ - Pets are Allowed. Prior written approval required. Number of Pets: 1 Types: Approved cat Miso, domestic shorthair, 11 lb (2026-01-25). Maximum Weight (per pet): 50 Pounds One-time pet fee: $250.00, nonrefundable; monthly pet rent: $0.00." [S2].
- `Q06` — **PASSED**: Assertions passed.
  - Response status: `needs_clarification`; latency: 0.014625s; tools: retrieval.
- `Q07` — **PASSED**: Assertions passed.
  - Response status: `needs_clarification`; latency: 0.013490s; tools: retrieval.
- `Q08` — **PASSED**: Assertions passed.
  - Response status: `needs_clarification`; latency: 0.013006s; tools: retrieval.
- `Q09` — **PASSED**: Assertions passed.
  - Response status: `needs_clarification`; latency: 0.014069s; tools: retrieval.
- `Q10` — **PASSED**: Assertions passed.
  - Response status: `denied`; latency: 0.004931s; tools: none.

## LIVE evaluation

Generated (UTC): 2026-11-06T16:36:41.561719+00:00

Questions executed: **10/10**. Passed: **9**; failed: **1**; not run: **0**; blocked: **0** (subset of not run).

| Metric | Result | Denominator |
|---|---:|---:|
| tool_selection_accuracy | 1.0000 (10/10) | 10 |
| calculation_exact_match | NOT_MEASURED (0/0) | 0 |
| citation_correctness | 1.0000 (5/5) | 5 |
| groundedness_structural | 1.0000 (5/5) | 5 |
| returned_citation_correctness | 1.0000 (5/5) | 5 |
| answer_factual_support_rubric | 0.8000 (4/5) | 5 |
| abstention_clarification_correctness | 1.0000 (4/4) | 4 |
| authorization_correctness | 1.0000 (1/1) | 1 |
| recall_at_5 | 0.7143 | 7 |
| precision_at_5 | 0.2000 | 7 |
| overall_case_pass_rate | 0.9000 (9/10) | 10 |
| latency_seconds | average 12.023124s; median 12.931261s | 10 |

Cases with no ground-truth chunks: Recall@5 is **NOT_MEASURED**, not zero or a guessed score. Citation correctness includes expected answer/calculation cases with missing citations as failures. Returned-citation correctness scores only cases that actually returned citations.


### Per-question outcomes and failure examples

- `Q01` — **PASSED**: Assertions passed.
  - Response status: `supported`; latency: 11.343692s; tools: retrieval.
- `Q02` — **PASSED**: Assertions passed.
  - Response status: `supported`; latency: 10.061242s; tools: retrieval.
- `Q03` — **PASSED**: Assertions passed.
  - Response status: `supported`; latency: 16.202605s; tools: retrieval.
- `Q04` — **PASSED**: Assertions passed.
  - Response status: `supported`; latency: 10.086542s; tools: retrieval.
- `Q05` — **FAILED**: answer_reference, reference_evidence_coverage, factual_support
  - Response status: `supported`; latency: 12.770409s; tools: retrieval.
  - Actual answer: For “Are pets allowed”, the lease evidence states "8.1 One pet weighing up to 50 pounds is permitted with prior written approval and a one-time $250 pet fee. The resident remains responsible for pet-related damage as described in section 4.2." [S1].  For “what happens if my pet damages the apartment?”, the lease evidence states "8.1 One pet weighing up to 50 pounds is permitted with prior written approval and a one-time $250 pet fee. The resident remains responsible for pet-related damage as described in section 4.2." [S2].
- `Q06` — **PASSED**: Assertions passed.
  - Response status: `needs_clarification`; latency: 15.974503s; tools: retrieval.
- `Q07` — **PASSED**: Assertions passed.
  - Response status: `needs_clarification`; latency: 14.489722s; tools: retrieval.
- `Q08` — **PASSED**: Assertions passed.
  - Response status: `needs_clarification`; latency: 13.092114s; tools: retrieval.
- `Q09` — **PASSED**: Assertions passed.
  - Response status: `needs_clarification`; latency: 16.205376s; tools: retrieval.
- `Q10` — **PASSED**: Assertions passed.
  - Response status: `denied`; latency: 0.005032s; tools: none.


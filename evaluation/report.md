# LAGA MVP evaluation report

## Method and limitations

All assertions are deterministic automated checks; no LLM judge or confidence score is used.
Golden reference assertions were agent-authored from the synthetic unsigned PDF; unknown references must be marked
needs_annotation. No independent legal or end-to-end human answer-quality review was performed.
Mock retrieval uses transparent topic rules, NOT Pinecone or embeddings; its scores are fixture diagnostics,
not live RAG performance. The authorization denial uses real backend ownership methods against a disposable
SQLite fixture in mock mode, not an authenticated browser/session test.
Recall@5 and Precision@5 use the first five unique chunks in first-seen subquestion/retry order.
Scores are macro-averaged over executed cases with nonempty reference chunk annotations; Precision@5 always
divides by five, including empty slots. Reference sets are selected, not exhaustive: precision is provisional
against those annotations. Repeated retries are captured but are not counted as independent questions.
Citation correctness compares source metadata, scope, references and literal quotes against returned evidence.
Groundedness is structural excerpt support only, NOT semantic entailment or legal correctness; fee arithmetic
is checked separately with Decimal. Clarification uses an explicit abstention/uncertainty lexical check.
Answer references use stated substring assertions, not full natural-language equivalence.
Latency includes per-case authorization, graph compilation, retrieval/retries and tools; excludes corpus
preparation and global live preflight. No live provider latency is claimed for mock runs.
Disabled/unverified live runs are NOT_RUN / BLOCKED, never PASSED. Missing-annotation cases are NOT_RUN.
No snapshot/binding approval, re-ingestion, flag changes, or application code rewrites are performed.

## MOCK evaluation

Generated (UTC): 2026-11-06T05:14:12.238742+00:00

Questions executed: **15/15**. Passed: **11**; failed: **4**; not run: **0**.

| Metric | Result | Denominator |
|---|---:|---:|
| tool_selection_accuracy | 0.8667 (13/15) | 15 |
| calculation_exact_match | 0.0000 (0/2) | 2 |
| citation_correctness | 0.8333 (10/12) | 12 |
| groundedness_structural | 0.8333 (10/12) | 12 |
| abstention_clarification_correctness | 0.5000 (2/4) | 4 |
| authorization_correctness | 1.0000 (1/1) | 1 |
| recall_at_5 | 1.0000 | 12 |
| precision_at_5 | 0.2833 | 12 |
| latency_seconds | average 0.011975s; median 0.012141s | 15 |

### Per-question outcomes and failure examples

- `simple-01` — **PASSED**: Assertions passed.
- `simple-02` — **PASSED**: Assertions passed.
- `simple-03` — **PASSED**: Assertions passed.
- `simple-04` — **PASSED**: Assertions passed.
- `simple-05` — **PASSED**: Assertions passed.
- `multi-01` — **PASSED**: Assertions passed.
- `multi-02` — **PASSED**: Assertions passed.
- `multi-03` — **PASSED**: Assertions passed.
- `fee-01` — **FAILED**: tools, calculation, citations, groundedness, reference_evidence_coverage, behavior
  - Actual answer: I can’t answer from the authorized lease evidence available. Please provide the missing lease clause or clarify the question. The contractual late-fee clause is conditional or ambiguous.
  - Fee extraction errors: The contractual late-fee clause is conditional or ambiguous.
- `fee-02` — **FAILED**: tools, calculation, citations, groundedness, reference_evidence_coverage, behavior
  - Actual answer: I can’t answer from the authorized lease evidence available. Please provide the missing lease clause or clarify the question. The contractual late-fee clause is conditional or ambiguous.
  - Fee extraction errors: The contractual late-fee clause is conditional or ambiguous.
- `missing-01` — **FAILED**: abstention, behavior
  - Actual answer: For “What exact NSF charge must I pay?”, the lease evidence states "7. NSF FEE. (check one)  ☐ - No NSF Fee.  ☐ - NSF Fee: $____________" [S1].
- `missing-02` — **FAILED**: abstention, behavior
  - Actual answer: For “What exact parking charge must I pay?”, the lease evidence states "13. PARKING. (check one)  ☐ - No Parking Provided.  ☐ - Parking is Provided. _____ parking spaces are provided with: (check one) ☐ - No Fee. ☐ - Fee (describe). ________________________" [S1].
- `unsupported-01` — **PASSED**: Assertions passed.
- `authorization-01` — **PASSED**: Assertions passed.
- `legal-01` — **PASSED**: Assertions passed.

## LIVE evaluation

Generated (UTC): 2026-11-06T05:10:30.059927+00:00

Questions executed: **0/15**. Passed: **0**; failed: **0**; not run: **15**.

| Metric | Result | Denominator |
|---|---:|---:|
| tool_selection_accuracy | N/A (0/0) | 0 |
| calculation_exact_match | N/A (0/0) | 0 |
| citation_correctness | N/A (0/0) | 0 |
| groundedness_structural | N/A (0/0) | 0 |
| abstention_clarification_correctness | N/A (0/0) | 0 |
| authorization_correctness | N/A (0/0) | 0 |
| recall_at_5 | N/A | 0 |
| precision_at_5 | N/A | 0 |
| latency_seconds | N/A | 0 |

### Per-question outcomes and failure examples

- `simple-01` — **NOT_RUN**: BLOCKED: live retrieval is disabled.
- `simple-02` — **NOT_RUN**: BLOCKED: live retrieval is disabled.
- `simple-03` — **NOT_RUN**: BLOCKED: live retrieval is disabled.
- `simple-04` — **NOT_RUN**: BLOCKED: live retrieval is disabled.
- `simple-05` — **NOT_RUN**: BLOCKED: live retrieval is disabled.
- `multi-01` — **NOT_RUN**: BLOCKED: live retrieval is disabled.
- `multi-02` — **NOT_RUN**: BLOCKED: live retrieval is disabled.
- `multi-03` — **NOT_RUN**: BLOCKED: live retrieval is disabled.
- `fee-01` — **NOT_RUN**: BLOCKED: live retrieval is disabled.
- `fee-02` — **NOT_RUN**: BLOCKED: live retrieval is disabled.
- `missing-01` — **NOT_RUN**: BLOCKED: live retrieval is disabled.
- `missing-02` — **NOT_RUN**: BLOCKED: live retrieval is disabled.
- `unsupported-01` — **NOT_RUN**: BLOCKED: live retrieval is disabled.
- `authorization-01` — **NOT_RUN**: BLOCKED: live retrieval is disabled.
- `legal-01` — **NOT_RUN**: BLOCKED: live retrieval is disabled.


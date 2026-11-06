# LAGA MVP evaluations

The current dataset is **Q01–Q10**, documented in
`DATASET_ANNOTATIONS.md`. Check each report's execution mode, generation time
and dataset fingerprint before comparing results.

Run the final 10-question **OFFLINE** evaluation without inheriting workspace secrets:

```sh
node scripts/run-isolated-tests.mjs evals
```

This invokes the existing `agent.graph.build_graph().invoke()` interface, real
fee calculator, actual PDF chunker and real backend ownership methods against a
disposable synthetic SQLite fixture. It does not call Pinecone, any LLM, or an
embedding service. The mocked retriever selects actual PDF chunks by explicit
topic rules, independently of golden expected chunk IDs.

Run live evaluation **only when intentionally requested**:

```sh
PYTHONPATH=src:. .pythonlibs/bin/python -m evaluation.run_evals --mode live
```

For an explicitly approved isolated synthetic-demo evaluation while the
application remains disabled:

```sh
PYTHONPATH=src:. python -m evaluation.run_evals --mode live --isolated-demo
```

This passes reviewed activation flags only to an in-memory configuration.
It does not change Replit environment configuration or the running app.
The real production factory still validates approved bindings, snapshot,
canonical corpus, ownership and both indexes. Failure never substitutes
offline fixtures.

The live runner does not enable anything. If retrieval is disabled or local
production prerequisites fail, all live cases are recorded as `NOT_RUN` with a
`BLOCKED` reason. When enabled, it uses a read-only connection to the configured
backend SQLite DB, existing backend principal/lease authorization and
`ProductionRetrieverFactory` including its approved binding, snapshot, corpus,
canonical citation and index validation. It never calls ingestion/index creation.
No fixture fallback is allowed. A successful local preflight alone is not proof
that service access will succeed; service failures remain evaluation failures.

Q10 executes `BackendAPI.post_assistant_messages()` and must be denied before
retrieval. Positive graph outcomes pass through the existing `adapt_answer()`
and Answer schema for actual public response status. These are service-level
evaluations, not browser/session tests. The explicit factual-support rubric
checks annotated answer facts, source provenance and required clause coverage;
it is not an unverified model self-score or independent human legal review.
Run `evaluation/test_evals.py` with the existing secret-isolated test machinery.

The cases are three simple questions, two multi-clause questions, two fee
questions, two missing-evidence questions (Wi-Fi and personal phone password), and one tenant
authorization denial. Expected facts and reference chunk IDs come from the
hash-pinned canonical synthetic PDF. Fees use explicit hypothetical payment
facts and independently specified Decimal expectations. Current Q06 is
clarification-first under existing extraction requirements; its USD 50 reference
is conditional, not a mandatory calculator invocation. Q07 lacks a payment date.

`results.json` preserves separate `mock` (labeled **OFFLINE**) and `live` runs. `report.md` summarizes
actual results, denominators, limitations and failures. The CLI returns 0 when a
report was generated (even with failing assertions or blocked cases), and 2 when
the runner itself cannot complete. Inspect reported outcomes for quality gates.
Re-running offline mode preserves a previously recorded live run only when its
dataset fingerprint matches. Stale runs from the earlier 15-case dataset are
not combined with final 10-case results. The CLI also accepts `--mode offline`
as an alias for the existing `mock` mode.

All monetary values are USD decimal strings; percentages, where used, are
percentage points. Payment dates in questions are hypothetical user-supplied
inputs, not claims about recorded payments. Reference amounts are manually
annotated expectations checked with Decimal, not outputs copied from the tool.

The PDF hash pins the real public unsigned fixture, and the manifest fixture pins
its declared identity. References come from actual local chunk extraction, not a
reconstructed ingestion snapshot. Do not call this fixture signed or enforceable.
Unverifiable answers must use `annotation_status: "needs_annotation"`; they are
not scored as passing. Do not modify chunks to make an evaluation pass.

Results contain source excerpts and metadata. The checked-in dataset is restricted
to the public synthetic fixture. Do not substitute real tenant data into distributable
reports. A future private dataset needs private output handling and human review.

Recall@5 uses first-seen unique returned chunks across subquestions/retries,
not an independent global ranking. Cases without annotated chunks are
`NOT_MEASURED`; aggregate retrieval scores exclude those cases. Citations are
checked as exact excerpts on verified source pages, including Phase 8H's
narrowed quotes. A reported failure is not permission to alter production
prompts, answerability rules, or the calculator to improve this dataset's score.

The offline topic selector is deliberately limited: it may return only template
sections and omit operative clauses elsewhere in the combined PDF. Thus an
offline failure can differ from a successful live Pinecone retest. All measured
latencies in an OFFLINE report are fixture/graph execution times, not provider
or UI response times.

# LAGA MVP evaluations

Run the 15-question deterministic mock evaluation without inheriting workspace secrets:

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

The live runner does not enable anything. If retrieval is disabled or local
production prerequisites fail, all live cases are recorded as `NOT_RUN` with a
`BLOCKED` reason. When enabled, it uses a read-only connection to the configured
backend SQLite DB, existing backend principal/lease authorization and
`ProductionRetrieverFactory` including its approved binding, snapshot, corpus,
canonical citation and index validation. It never calls ingestion/index creation.
No fixture fallback is allowed. A successful local preflight alone is not proof
that service access will succeed; service failures remain evaluation failures.

`results.json` preserves separate `mock` and `live` runs. `report.md` summarizes
actual results, denominators, limitations and failures. The CLI returns 0 when a
report was generated (even with failing assertions or blocked cases), and 2 when
the runner itself cannot complete. Inspect reported outcomes for quality gates.
Re-running mock mode through the launcher preserves a previously recorded live
run; check each run's timestamp before comparing results.

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

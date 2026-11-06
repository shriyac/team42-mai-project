# Final evaluation preservation

The Phase 9B Q01–Q10 artifacts are preserved for submission without rerunning
live retrieval or changing production behavior.

## Verified artifacts

- `evaluation/golden_questions.json`: annotated Q01–Q10 dataset.
- `evaluation/run_evals.py`, `evaluation/fixtures.py`, `evaluation/metrics.py`:
  existing graph/backend evaluation harness and explicit source/fact rubric.
- `evaluation/test_evals.py`, `tests/test_evaluation.py`,
  `tests/test_golden_dataset.py`: harness, reporting and annotation regressions.
- `evaluation/results.json`, `evaluation/report.md`: actual separately labeled
  OFFLINE and LIVE runs with matching dataset fingerprints.
- `evaluation/README.md`, `evaluation/DATASET_ANNOTATIONS.md`: methods,
  provenance, conditional fee reference and interpretation limitations.

Saved assertions, retrieval metrics, aggregate denominators and latency
statistics were recomputed from the recorded outcomes. Seven OFFLINE and 70
LIVE retrieved records match the public synthetic canonical source.

## Results retained without modification

| Mode | Passed | Failed | Blocked / not run |
|---|---:|---:|---:|
| OFFLINE | 6/10 | 4/10 | 0 / 0 |
| LIVE | 9/10 | 1/10 | 0 / 0 |

LIVE Q05 remains a documented completeness failure: the answer states pet-damage
responsibility but omits the ordinary-wear/documented-damage condition and
required section 4.2 evidence. The strict selected-reference rubric can also
reject equivalent passages, as illustrated by OFFLINE Q02.

Calculation exact-match remains **NOT_MEASURED, denominator 0**. Neither fee
case called the calculator; the conditional USD 50 reference is not an executed
numeric answer. These scores are not claims of general legal correctness,
independent human review, authenticated browser performance or unrestricted
production readiness.

## Preservation regression rerun

- Python: **333 passed + 57 subtests**, one dependency deprecation warning.
- This full run includes the **27 evaluation/dataset tests**.
- Frontend: **46 passed**.
- API-mode production build: **passed**.

Tests ran in the existing secret-isolated source copy. Phase 9C did not call
Pinecone, enable retrieval, change application flags, ingest data or modify the
production agent, retrieval algorithms, authentication or calculator.

## Release safety

Current and previously exposed credential comparisons and credential-pattern
checks passed without printing sensitive values. Result evidence was checked
against the public fictional corpus rather than treated as private tenant data.

Only reviewed evaluation files, tests and documentation are included. Local
checkpoint history is retained on a local safety branch; Replit-generated
asset metadata, Secrets, dotenv files, session material, generated databases,
bootstrap credentials, private bindings, operational snapshots and logs are
excluded. The release is based on the existing remote integration tip and
requires no force push or merge. Local `main` and teammate branches are untouched.

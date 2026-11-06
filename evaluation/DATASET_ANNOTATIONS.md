# Q01–Q10 annotation review

These annotations were prepared without running evaluations. Execution results
are recorded separately in `results.json`/`report.md`; their dataset fingerprint
must match Q01–Q10 before they can be presented as scores for these questions.
The runner prevents mixing reports from different datasets.

The canonical PDF SHA-256, unchanged ingestion manifest, genuine local snapshot
and existing `verify_corpus()` ledger were checked locally without Pinecone.
All ten cases have verified annotations; none currently require annotation.
“Verified” means agent-reviewed source/requirement checks, not independent human
review or legally enforceable terms. The document remains synthetic unsigned.

| Case | Ground truth |
|---|---|
| Q01 | Section 3, PDF p.1: end date 2027-01-31 inclusive |
| Q02 | Source annexure A 8.1, PDF p.22: one pet, 50 lb, written approval |
| Q03 | Selected section 6 options, PDF p.1: $50 after day 5, once per installment |
| Q04 | Section 3 p.1 and source deposit record 4.2 p.18 |
| Q05 | Source annexure A 8.1 p.22 and deposit record 4.2 p.18 |
| Q06 | Sections 4 and 6 p.1; current extraction requires clarification |
| Q07 | Sections 4 and 6 p.1; payment date and other installment facts absent |
| Q08 | No verified Wi-Fi password; no invented positive chunk mapping |
| Q09 | No verified personal phone password; no invented positive chunk mapping |
| Q10 | Actual SQLite and synthetic bootstrap ownership deny tenant-1/lease-2 |

Every cited excerpt is checked against its canonical chunk and actual PDF page.
Source annexures retain canonical section 28 metadata; the original subsection
numbers are explanatory labels, not rewritten citation identities.

Q06 distinguishes a calculator reference from a workflow requirement. Given
validated USD 2200 monthly rent, USD 50 contractual flat fee, 2026-11-01 due date,
2026-11-06 payment and no prior fee, the existing Decimal calculator returns
USD 50 with a USD 110 cap. However, the current extractor rejects the question's
date wording and conditional clause. Its expected workflow behavior is therefore
clarification, no calculator call, and no published numerical result. This is a
documented implementation limitation, not an assertion that the PDF fee is absent.
Revisit this annotation explicitly if extraction requirements change.

Q07 must not use the reference date to invent a payment date. Negative password
cases are corpus-bounded absence assertions, not claims about anyone's actual
credentials. Q10 is an authorization refusal, not an attempt to retrieve another
tenant's PDF. No refunds, present balances, statutory deadlines, or unspecified
charges are invented.

# Answerability validation

## Root cause

Planning splits questions into subquestions. Monica's hybrid retriever returns
ranked, tenant-authorized candidates, not a guarantee that any passage answers a
question. Previously the default generator formatted every candidate as an
answer. Validation checked source identity and citation markers, but not
question-to-evidence relations. `adapt_answer()` consequently mapped a passed
validation to `supported`, even for an absent Wi-Fi password.

## Boundary

`agent/answerability.py` defines a deliberately limited deterministic lease
intent/statement gate. It does not claim general semantic entailment.
Unsupported or unknown requests fail closed. Each required question part must
have a responsive statement; source ownership, scores and keyword overlap alone
are insufficient. Optional generated claims must also be extractive and match
the document referenced by each citation marker.

The default generator selects exact, concise excerpts from verified source
spans, preserving their PDF pages and immutable document/clause identities.
Unchecked template options and incomplete fragments cannot establish operative
terms. The graph revalidates excerpt provenance and relevance; the backend
independently checks narrowed quotes against server-recorded source spans.
Retrieval diagnostics retain authorized candidates, but abstentions publish no
citations. The existing graph permits one targeted retry, then maps abstention
to the existing backend `needs_clarification` status.

## Verification

Final local run: 313 Python tests and 57 subtests passed; 46 frontend tests
passed; API-mode production build passed. Existing security regressions are
included. One existing Starlette deprecation warning remains.

Read-only live retesting used a test-only configuration, real production
retrieval factory and SQLite `mode=ro`; application activation flags stayed off:

| Request | Result | Seconds |
|---|---|---:|
| Wi-Fi password | needs_clarification; no citations; one retry | 12.358 |
| Lease expiration | supported; term, PDF page 1 | 9.924 |
| Pets | supported; operative prior-approval/50 lb/$250 clause, page 22 | 10.051 |
| End date and deposit | supported; term page 1, damage deductions page 18 | 10.516 |
| Late-payment terms | supported; selected $50/day-5/once-per-installment terms, page 1 | 9.804 |

Synthetic unsigned disclosure remains intact. No fee computation was requested
in this live retest; the calculator implementation is unchanged. These results
do not verify an interactive signed-in browser session or automatically
authorize broad production activation. Shared statutes remain excluded from
the lease-only backend answer path.

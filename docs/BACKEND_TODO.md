# Backend implementation and review checklist

The SQLite methods are implemented in `src/laga/backend_api.py`; see [method reference](BACKEND_METHODS.md). Keep the keyword names and return DTOs unchanged. Do not return HTTP response objects from this class. The adapter owns cookies, envelopes, bounded parsing and schema validation. Every business operation re-reads server account membership; client-supplied organization/role fields are never an authorization source.

## Route-to-method handoff

| UI call | HTTP route | BackendAPI method | Current state |
| --- | --- | --- | --- |
| login | POST /auth/login | post_auth_login | Implemented |
| getSession | GET /auth/session | get_auth_session | Implemented |
| logout | POST /auth/logout | post_auth_logout | Implemented |
| getWorkspace | GET /workspace | get_workspace | SQLite implemented |
| getLease | GET /leases/{id} | get_leases_id | SQLite implemented |
| createProperty | POST /properties | create_property | SQLite implemented |
| ask | POST /assistant/messages | post_assistant_messages | TODO B04: explicit 503 |
| createRequest | POST /requests | post_requests | SQLite implemented |
| replyRequest | POST /requests/{id}/reply | post_requests_id_reply | SQLite implemented |
| uploadPolicy | POST /policies | post_policies | Private storage/versioning implemented; pipeline pending |
| deletePolicy | DELETE /policies/{id} | delete_policies_id | SQLite implemented |

`get_user_id`, `provision_user` and `import_lease` are internal/admin helpers, not additional HTTP endpoints. `listDemoUsers` belongs only to the mock UI adapter.

## B04: assistant implementation

- Replace only `post_assistant_messages` initially. Authorize organization, lease and conversation ownership before retrieval; use 404 for foreign/invisible IDs. Bind thread scope and date server-side.
- Resolve property/state and half-open policy dates before every retrieval branch, cross-reference expansion and cache lookup. A blocked effective replacement must not revive its expired predecessor.
- Return needs_clarification for insufficient/conflicting evidence. Cite exact immutable document versions, quotes and pages. Compute integer-cent calculations deterministically.
- Connect `src/laga/compliance.py` and a real reviewer according to the agreed backend review configuration. The UI flag is not a client-controlled backend bypass. Bind final answer review to exact content, scope, date and law revision.
- Return the canonical Answer DTO. Never copy a synthetic passed-review fixture into real output. Verify final response through adapter validation and the API Explorer.

## B07: document pipeline

- Poll/claim uploaded rows transactionally, or integrate a durable job queue. Validate actual PDF structure, native text/OCR policy, malware and extraction completeness. Treat document text as untrusted content.
- Persist immutable extraction outputs, checksums, page anchors, index versions and failure details privately. Commit all required indices before setting ready. Set failed visibly on processing failure.
- Keep normalized `policies.status` and the JSON DTO's status, excerpt, pageCount and compliance metadata consistent in one transaction. No public status setter is supplied by this scaffold.
- Validate jurisdiction against authorized properties and enforce required legal review independently of processing readiness. Keep family timezone and revision bytes immutable.
- Add worker tests for duplicate jobs, restart recovery, partial failure and effective-but-unready replacements. Metadata upload success is not evidence of ingestion success.

## Administrative and operational integration

- Establish account lifecycle, password reset/deactivation, MFA/identity provider requirements, and role provisioning policy. Use explicit stable organization membership IDs; do not infer membership from display names or email domains.
- Import authorized real lease/ledger data through the trusted helper or your own transaction layer. The scaffold does not seed a ledger or attest payment receipt. `paymentStatus=due` is an imported input; outstandingRent is a UI summary of those imported flags, not a financial reconciliation.
- Decide whether replies require immutable threaded history; the current DTO supports one current reply and this implementation replaces it.
- Introduce reviewed schema migrations, database access permissions, encryption/backup/restore procedures and retention controls for PDF and cancellation audit BLOBs. Move to production storage/DB if deployment scale requires it.
- Configure HTTPS, exact Origin allowlists, cookie policy and trusted reverse proxies; run the same session/CSRF tests against that topology. Add operational request correlation, monitoring and dependency locking for your deployment.
- Run Python/frontend tests and build. Use the Explorer and actual UI in API mode with separate tenant and landlord sessions; test different organizations, stale policy writes, cancellation, expired sessions and ingestion failures.

## Test review and first-run behavior

The prior three-loop findings remain in [BACKEND_TEST_REVIEW.md](BACKEND_TEST_REVIEW.md). Default application startup now automatically seeds fictional development accounts, lease PDFs and policy PDFs, as documented in [BOOTSTRAP.md](BOOTSTRAP.md). A random per-installation password is saved locally; no manual first-run data setup is required. Existing populated databases are preserved. External assistant/document pipelines remain unimplemented.

# Laga frontend / Python interface contract v1.1

The machine-readable source is ../contracts/openapi.json (OpenAPI 3.1). The frontend gateway interface is frontend/src/services/httpGateway.js. Both adapters have contract-tested response shapes. Use `/api/v1` under the same origin.

## Transport and authentication

Success responses are `{ "data": <DTO> }`, including logout and DELETE. Do not return an empty 204 response. Failures use `{ "error": { "code": "VERSION_CONFLICT", "message": "This policy changed. Refresh the library before adding a version.", "requestId": "req-unique", "fields": {} } }`. IDs are opaque stable strings; never derive authorization from their format.

GET /auth/session returns a Session; anonymous visitors receive user:null and csrfToken:null, not 401. POST /auth/login receives email/password and returns Session. The UI's customer/landlord selector is a presentation hint: the server determines the role and permissions. Use Secure, HttpOnly, SameSite cookies in production, session rotation at login, CSRF protection (including login via origin checks or a pre-auth token), password hashing, rate limiting and generic invalid-login messages. Never return password hashes or accept client-supplied permissions. POST /auth/logout invalidates the session and returns data:{signedOut:true}. Authenticated mutations carry X-CSRF-Token from Session. The frontend sends credentials:include. 401 clears the visible workspace; 403 preserves it and reports the denied action. Tenant requests for foreign objects should return 404 to avoid disclosing their existence.

Return safe messages, field-level validation details and a requestId. Never send stack traces or internal storage paths. 400 malformed input, 401 unauthenticated, 403 forbidden, 404 invisible/missing object, 409 state/version conflict, 413 file too large, 422 validation failure, 429 rate limit, 503 unavailable. JSON schemas describe DTOs; enforce lengths, enums, ownership and file validation server-side too.

## Gateway methods and routes

| Gateway | Request | Result DTO |
| --- | --- | --- |
| login({email,password}) | POST /auth/login JSON | Session |
| getSession() | GET /auth/session | Session |
| logout() | POST /auth/logout | Logout |
| createProperty({name,address,city,state,units}) | POST /properties JSON | Property |
| getWorkspace() | GET /workspace | Workspace |
| getLease(id) | GET /leases/{id} | LeaseDetail |
| ask({question,scope,asOf,threadId}) | POST /assistant/messages JSON | Answer |
| createRequest({leaseId,category,subject,message}) | POST /requests JSON | Request |
| replyRequest(id,{reply}) | POST /requests/{id}/reply JSON | Request |
| uploadPolicy(fields) | POST /policies multipart/form-data | PolicyVersion |
| deletePolicy(id) | DELETE /policies/{id} | Deleted |

`listDemoUsers()` is mock-only and performs no API call. Demo login's role/tenantId are also mock-only. HTTP mode sends email/password only. No browser-stored access tokens are used.

Workspace includes user, asOf (server business date), timeZone (IANA, preview America/Chicago), summary, properties, leases, tenants, requests and policy versions. Each tenant sees only authorized records. Landlord access is organization-scoped. All monetary values and tool inputs/results use integer minor units (USD cents here). ISO date strings represent calendar dates, not instants; uploadedAt and createdAt are ISO timestamps with offsets. Currency is explicit. Missing/unknown values must not silently become zero.

Portfolio statistics must be calculated from the same authorized active lease set returned to the UI. Occupancy counts occupied units, not merely lease rows if multiple leaseholders are introduced. The sample has one lease per occupied unit, 10 residents, 12 units and three properties. List DTOs currently assume a small portfolio; production pagination/search will require a coordinated contract extension.

## Policy families, versions and effective dates

A family is one policy's identity across versions. PolicyVersion.id is a unique immutable revision ID, familyId is stable, version is monotonically increasing. Title, category and property scope remain fixed within the family. A propertyId of null means organization-wide. Multiple families and categories may apply simultaneously; property-specific policies do not silently override global policies. Explicit precedence/conflict rules need a future contract if desired.

A version applies when effectiveFrom <= asOf AND (effectiveTo IS NULL OR asOf < effectiveTo). End dates are exclusive. For example, v1 [2026-01-01,2026-11-15) and v2 [2026-11-15,null) have exactly one applicable version on November 15: v2. Show the old end as 'until before November 15' to avoid ambiguity. Interpret calendar dates in the policy's immutable property time zone or the organization time zone for global policies. Persist that time zone with the policy family even though this frontend's Workspace supplies the display context.

Uploading a new version takes file, state, familyId, expectedVersion and effectiveFrom. New families take file, state, title, category, optional propertyId and effectiveFrom. Existing families inherit title/category/scope. Validate a real calendar date. Only append chronological versions: no earlier than today's server business date, and strictly later than the latest version's start. Retroactive corrections are not supported by this UI.

Within one database transaction, lock the family, verify expectedVersion matches the latest revision (otherwise 409 VERSION_CONFLICT), append vN+1, and set vN.effectiveTo to the new start. Use a uniqueness constraint on (familyId,version), enforce non-overlap and protect concurrent writes. Old bytes, checksums, extraction outputs, uploader identity and citations remain immutable for audit. Separate uploaded timestamp from policy effective date.

A future version is scheduled; it does not replace the current policy early. At its start, the predecessor is ineligible even if the new file has not finished processing. Warn administrators before activating an unready policy. Return a clear 'policy ingestion unavailable' clarification result; never silently retrieve the expired version. Ingestion failure must remain visible and require retry or a later corrected version, not a rollback of history.

DELETE is narrowly a cancellation operation: only the latest future non-ready version with no successor may be canceled. Restore its predecessor's previous open-ended boundary atomically. Effective/current versions and ready historical revisions cannot be deleted. Keep a separate cancellation audit record in the backend even if the workspace hides the canceled revision. The UI stages `awaiting_backend` only in mock mode; Python uses uploaded -> processing -> ready or failed. Ready means validated extraction and all required indices are committed. No partial-ready retrieval.

Validate file size (max 10 MiB), PDF magic/type, native text availability, malware policy and safe filename/storage handling. The browser extension filter is only a convenience. Store uploaded bytes privately, never in public frontend assets. Return metadata promptly and process asynchronously. The current UI uses Refresh to reload ingestion status; polling, job progress and retries are future extensions. No actual file contents are stored in mock mode.

## Retrieval and citations

The request carries scope:{type:'lease',id:'lease-1'} or scope:{type:'portfolio',id:null}, a required asOf date and an optional threadId. Bind thread ownership and scope/date server-side; changing date/scope creates a separate UI thread. Do not trust threadId for access.

Resolve authorization, property scope and policy interval before vector/hybrid search, reranking, cross-reference expansion, caching and answer synthesis. Every retrieval branch must preserve those filters. Include lease ownership, organization ID, revision ID and date/scope in cache keys. For a pending applicable version, stop and clarify rather than expanding to older versions. If multiple applicable versions in one family exist, report an integrity error and fail closed.

Citations contain documentId (revision ID for policies), title, section, page, exact quote, and policy version/effectiveFrom/effectiveTo where relevant. Answers must use only authorized applicable sources. Return status needs_clarification for missing evidence, conflicts, ambiguity or unready ingestion. The UI displays citations and user-safe activity labels, never private model chain-of-thought. Calculations expose deterministic inputs, method label, currency and integer-cent result; do not eval client-provided expressions.

Future PDF downloads should use an authorized endpoint or short-lived scoped URL. The current UI deliberately shows excerpts instead of fake download buttons. Uploaded contracts/policies must be treated as untrusted document content rather than executable instructions.

## Backend acceptance checklist

Implement all routes and response envelopes; run generated OpenAPI validation plus backend endpoint tests. Verify tenant isolation, landlord organization isolation, session/CSRF behavior, upload concurrency, effective-date boundaries, pending/failed fail-closed retrieval, cancellation audit, file validation and immutable citations. Switch VITE_LAGA_MODE=api and test the same flows without modifying components. No API error may silently activate mock data. Authentication, retention, legal review, ingestion, actual RAG and operational observability remain backend work; the current UI is not evidence of their completion.


## NC state-law review (contract 1.1)

- `POST /properties` requires landlord policy-write permission and `name`, `address`, `city`, `units`, `state`. Only NC is configured initially. State is mandatory at first registration. The server owns the property record; tenants cannot override jurisdiction.
- `PolicyUpload.state` is mandatory on every corpus/version upload. Validate it against all scoped property records inside the authorized organization, including organization-wide scope. A policy family cannot change state. NC-only scope must not expand to properties in other states when properties are later added.
- Tenant and lease-scoped assistant requests derive jurisdiction from the authorized lease's property. Do not accept a tenant-supplied state. Portfolio questions requiring legal interpretation must be scoped and checked per property.
- Ingestion readiness and legal compliance are independent. A policy is eligible only when ingestion is ready AND compliance has passed for its exact content, scope, reference date and applicable law revision. Conflicts/pending/unavailable checks block retrieval; an effective blocked replacement must never revive the expired predecessor.
- Shared government source snapshots are fetched once per state and reused, with daily refresh. Store provenance, retrieval time, revision, effective-date coverage and hashes. Stale/unavailable or incomplete coverage blocks approval. `src/laga/compliance.py` implements caching and the default-deny reviewer boundary, not a legal reasoning model or API service.
- Recheck every newly uploaded PDF after extraction, even within an existing family; return clause-level findings and official statute citations. Treat uploaded text as untrusted evidence, never reviewer instructions. Bind the review to the immutable document hash and law revision. Never accept a client-provided compliance verdict.
- Validate the FINAL generated answer and calculations against applicable law before returning it, for both roles. Do not stream unchecked legal claims. Bind the answer review to the final text, reference date, property and law revision. A model confidence score is insufficient. Include authoritative citations; escalate conflicting/uncertain or unsupported matters for review. Federal/local rules and amendments not reflected in a cached chapter must be assessed too.
- The HTTP adapter withholds legacy `supported` responses lacking a passed review. This is a display safeguard; the API must enforce all checks before releasing content. The prototype has no connected reviewer and therefore provides no legal answers.


### Review identity and freshness

A passed answer review includes `kind: answer`, `scopeKey` (`lease:<id>` or `portfolio:all`), `state`, exact `asOf`, UTC `checkedAt` / `expiresAt`, 64-character SHA-256 `lawRevision` and `contentHash`, and official `citations` with statute sections. The frontend verifies the hash against the final answer text. The server must validate calculations together with that answer and authorize scope independently. Policy reviews use `kind: policy`, `scopeKey: property:<id>` or `state:NC`, and a hash matching `PolicyVersion.contentHash`. Missing, expired or mismatched metadata blocks use. A review for a different reference date cannot establish applicable law for the requested date. The Python review boundary now requires explicit `scope_key`.

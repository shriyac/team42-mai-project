# BackendAPI method reference

The implementation surface is `src/laga/backend_api.py`. Every method, including internal helpers, is documented here and in its docstring. Methods are synchronous; the HTTP adapter runs them in worker threads. `DTO` means a JSON-compatible dictionary whose exact fields are defined in `contracts/openapi.json`.

HTTP methods receive keyword arguments matching wire field names, including camelCase names such as `effectiveFrom`. They return unwrapped DTOs; `src/laga/api.py` adds `{data: ...}` and validates the result. The sole exception is login's internal `(Session, cookie_token)` tuple, which is converted to the standard Session envelope and Set-Cookie header. `user`, `session_token`, `client_key`, `filename` and `content_type` are trusted transport context, not extra JSON fields.

`APIError(status, code, message, fields=None)` is the public domain exception. HTTP translates it into `{error: {code, message, requestId, fields}}`. Unhandled storage/configuration/runtime errors become a safe 503 SERVICE_UNAVAILABLE; raw exceptions remain available to administrative Python callers. Response DTO violations become 503 BACKEND_CONTRACT_ERROR. Do not put secrets in exception messages. No business method takes or returns an SQL connection unless its name starts with `_`.

Default application startup now performs [automatic bootstrap](BOOTSTRAP.md); constructing BackendAPI directly still initializes schema only.

Use [BACKEND_IMPLEMENTATION.md](BACKEND_IMPLEMENTATION.md) for startup and [BACKEND_TODO.md](BACKEND_TODO.md) for remaining integration work.

## `__init__`

```python
__init__(self, database: str | Path, *, session_seconds: int = 28800, now=time.time, time_zone: str = "America/New_York")
```

**Purpose:** Initialize persistent account/session and portfolio tables, indexes and additive membership migration.

**Inputs:** database: filesystem SQLite path (not :memory:); session_seconds: integer absolute session lifetime from 1 through 2147483647 seconds, default 28800; now: injectable epoch-seconds clock; time_zone: IANA business timezone, default America/New_York.

**Output:** A BackendAPI instance; creates the parent directory and missing tables. No users or synthetic leases are seeded.

**Exceptions:** ValueError for invalid lifetime type/range, blank path or :memory: storage; ZoneInfoNotFoundError for unknown timezone; OSError/sqlite3.Error for inaccessible storage.

## `_connect`

```python
_connect(self)
```

**Purpose:** Open a short-lived SQLite connection.

**Inputs:** No arguments beyond self; uses the configured database path and a 10-second busy timeout.

**Output:** sqlite3.Connection owned by the caller. Use closing(connection) and a transaction context.

**Exceptions:** sqlite3.Error for unavailable or locked storage.

## `_digest`

```python
_digest(token: str) -> str
```

**Purpose:** Produce a one-way identifier for session tokens and rate-limit buckets.

**Inputs:** token: server-generated token or internal bucket string; never a password hashing function.

**Output:** Lowercase 64-character SHA-256 hexadecimal digest. No persistence.

**Exceptions:** No expected domain exceptions for a valid str; encoding/type errors for invalid caller input.

## `_hash_password`

```python
_hash_password(password: str, salt: str) -> str
```

**Purpose:** Derive a salted password verifier with scrypt (N=16384, r=8, p=1, dklen=32).

**Inputs:** password: UTF-8 string; salt: hexadecimal random salt. Provision/login enforce password byte limits.

**Output:** 64-character hexadecimal derived key; never the password.

**Exceptions:** ValueError for malformed salt or scrypt resource limits; MemoryError for exhausted memory.

## `provision_user`

```python
provision_user(self, *, user: DTO, password: str, organization_id: str) -> None
```

**Purpose:** Administratively create a local account with explicit organization membership; never exposed over HTTP.

**Inputs:** user: canonical User DTO with nonblank ID/name, a usable email of at most 320 characters, and server-approved role and permissions; password: 12+ characters, at most 1024 UTF-8 bytes; organization_id: nonblank internal organization key. Email is normalized. Tenant lease membership is established by import_lease, not by trusting display fields.

**Output:** None. Persists the User JSON, normalized email, random salt, scrypt verifier and internal organization key. Existing IDs/emails are never overwritten.

**Exceptions:** APIError 422 VALIDATION_ERROR for invalid User DTO; ValueError for invalid password/email/ID/name/organization; sqlite3.IntegrityError for duplicate ID/email; other storage errors propagate to administrative caller.

## `post_auth_login`

```python
post_auth_login(self, *, email: str, password: str, session_token: str | None,
                        client_key: str) -> tuple[DTO, str]
```

**Purpose:** Authenticate a locally provisioned account, rotate its browser session and return session metadata.

**Inputs:** email/password: LoginInput fields; session_token: existing browser cookie or None; client_key: trusted peer address from transport. Role/permissions never come from request fields. Rate limit: 10 attempts per account and peer in a rolling 15-minute window, including successes.

**Output:** (Session DTO, new raw cookie token). Session has user and csrfToken. Only the HTTP adapter places the raw token in an HttpOnly cookie; DB stores its digest. Previous browser token is revoked on successful login; lifetime is absolute.

**Exceptions:** APIError 401 INVALID_CREDENTIALS for unknown account, wrong/empty/oversized credentials; 429 RATE_LIMITED when either bucket is full; storage/hash errors propagate and HTTP maps them to safe 503.

## `get_auth_session`

```python
get_auth_session(self, *, session_token: str | None) -> DTO
```

**Purpose:** Resolve an unexpired session using current server-side account data.

**Inputs:** session_token: raw cookie string or None. Tokens longer than 128 characters are treated as anonymous.

**Output:** Session DTO: {user: User, csrfToken: str}; missing, revoked or expired tokens return {user: None, csrfToken: None}. Removes expired session rows without extending expiry.

**Exceptions:** No 401 for anonymous sessions. sqlite3.Error on storage failure (HTTP 503).

## `post_auth_logout`

```python
post_auth_logout(self, *, session_token: str | None) -> DTO
```

**Purpose:** Revoke the supplied session token.

**Inputs:** session_token: raw cookie or None. HTTP transport requires an authenticated session, allowed Origin and matching CSRF before calling this method; direct calls are internal.

**Output:** Logout DTO {signedOut: True}; HTTP clears the matching cookie. Internal revocation is idempotent even for unknown tokens.

**Exceptions:** sqlite3.Error for storage failure. HTTP guards can return 401/403 before this method executes.

## `_todo`

```python
_todo(operation: str) -> NoReturn
```

**Purpose:** Fail explicitly when an external backend capability is not connected.

**Inputs:** operation: safe internal operation name, never arbitrary user content.

**Output:** Never returns and performs no writes.

**Exceptions:** Always APIError 503 BACKEND_NOT_IMPLEMENTED.

## `get_user_id`

```python
get_user_id(self, *, session_token: str | None) -> str
```

**Purpose:** Return the authenticated user ID without accepting a client-selected identity.

**Inputs:** session_token: current raw session cookie or None. Internal helper, not an additional public HTTP route.

**Output:** Stable User.id string from get_auth_session.

**Exceptions:** APIError 401 UNAUTHENTICATED for missing/revoked/expired sessions; sqlite3.Error for storage failure.

## `_principal`

```python
_principal(self, db, user: DTO, *, role: str | None = None, permission: str | None = None)
```

**Purpose:** Re-read the authoritative account and organization for a service operation.

**Inputs:** db: open connection; user: transport-authenticated User DTO whose id is looked up again; role/permission: optional required server role and permission. Do not expose this direct-call boundary to untrusted callers.

**Output:** (current User DTO, internal organization_id). Caller-supplied role/permissions/organization are ignored.

**Exceptions:** APIError 401 UNAUTHENTICATED for missing account; 403 FORBIDDEN for missing organization membership or role/permission mismatch; sqlite3.Error.

## `_today`

```python
_today(self, time_zone: str | None = None) -> str
```

**Purpose:** Compute the current business calendar date independently of host timezone.

**Inputs:** time_zone: optional immutable policy-family IANA timezone; defaults to instance time_zone; uses injected clock.

**Output:** ISO YYYY-MM-DD string.

**Exceptions:** ZoneInfoNotFoundError for unknown timezone; ValueError/OverflowError for invalid clock values.

## `_timestamp`

```python
_timestamp(self) -> str
```

**Purpose:** Create a UTC timestamp for persisted events.

**Inputs:** No explicit input; uses the injected epoch clock.

**Output:** Offset-aware ISO timestamp string in UTC.

**Exceptions:** ValueError/OverflowError for invalid clock values.

## `_validate`

```python
_validate(schema: str, value: DTO)
```

**Purpose:** Validate a DTO against the canonical OpenAPI component schema.

**Inputs:** schema: component name, e.g. PolicyUpload; value: JSON-compatible dictionary. Reads contracts/openapi.json or LAGA_CONTRACT_PATH.

**Output:** None when valid; does not persist or sanitize data.

**Exceptions:** APIError 422 VALIDATION_ERROR with safe field messages for schema, unsafe integers or malformed text; 400 INVALID_JSON for nesting beyond 64 levels; OSError/JSONDecodeError for unavailable/broken contract; schema configuration errors for invalid references.

## `_lease`

```python
_lease(db, organization_id: str, user: DTO, id: str)
```

**Purpose:** Load a lease while concealing foreign-organization and foreign-tenant records.

**Inputs:** db: connection; organization_id: authoritative membership; user: server principal; id: opaque lease ID.

**Output:** (Lease DTO, list of Citation DTOs). Landlords remain organization-scoped; tenants must own the lease.

**Exceptions:** APIError 404 NOT_FOUND for missing or invisible lease; sqlite3.Error/JSONDecodeError for corrupt storage.

## `get_workspace`

```python
get_workspace(self, *, user: DTO) -> DTO
```

**Purpose:** Return one consistent SQLite-backed workspace for the authenticated principal.

**Inputs:** user: authenticated User DTO. No client organization, tenant selector or business date is accepted.

**Output:** Workspace DTO with demo=True for the bootstrapped fictional organization (False otherwise), asOf, timeZone, current user, properties, leases, tenants, requests, policy metadata and summary. Tenant records are filtered to their leases; landlord records to organization. Monetary sums are integer cents over active leases; occupied counts unique property/unit pairs; renewals count active leases ending in 0-90 days. PDF bytes and credential hashes are excluded.

**Exceptions:** APIError 401/403 via _principal; sqlite3.Error or malformed stored JSON/date errors on corrupt storage (safe HTTP 503).

## `get_leases_id`

```python
get_leases_id(self, *, user: DTO, id: str) -> DTO
```

**Purpose:** Return an authorized lease, property, tenant and source excerpts.

**Inputs:** user: authenticated User DTO; id: opaque lease ID. Requires lease:read for tenants or leases:read for landlords.

**Output:** LeaseDetail DTO with lease, property, tenant and clauses. No fabricated citations or automatic sample ingestion.

**Exceptions:** APIError 401/403 for account/permission issues; 404 NOT_FOUND for missing/invisible lease; 503 DATA_INTEGRITY_ERROR if referenced property/tenant is missing; storage errors.

## `create_property`

```python
create_property(self, *, user: DTO, name: str, address: str, city: str, state: str, units: int) -> DTO
```

**Purpose:** Persist an NC property owned by the authenticated landlord organization.

**Inputs:** user: authenticated landlord with policies:write; name (1-120), address (1-250), city (1-120): nonblank strings; state: NC; units: integer 1-10000. No organization or property ID is accepted from the client.

**Output:** Property DTO with generated UUID, trimmed text, immutable NC state, style=willow, empty amenities/description. Writes one row; no lease or occupancy is created.

**Exceptions:** APIError 422 VALIDATION_ERROR for schema/blank fields; 401/403 for principal/permission issues; sqlite3.Error.

## `import_lease`

```python
import_lease(self, *, organization_id: str, lease: DTO, clauses: list[DTO]) -> None
```

**Purpose:** Administratively import a lease with exact citations into the correct organization.

**Inputs:** organization_id: internal membership key; lease: canonical Lease DTO referencing an existing tenant and property in that organization; clauses: Citation DTO list whose documentIds belong to lease.documents. No HTTP route. Dates must be real and ordered; rent/deposit nonnegative JavaScript-safe integer cents; dueDay is 1-31 and noticeDays is nonnegative. Active portfolio rent must also remain JavaScript-safe.

**Output:** None. Inserts a lease and clauses atomically. Enforces one active lease per property/unit and property capacity. Does not modify account profile fields or seed synthetic data automatically.

**Exceptions:** APIError 422 for schema, date, amount, name or citation mismatch; 404 for missing/foreign tenant or property; 409 VERSION_CONFLICT for duplicate ID, active unit or capacity; sqlite3.Error.

## `post_assistant_messages`

```python
post_assistant_messages(self, *, user: DTO, question: str, scope: DTO, asOf: str,
                                threadId: str | None = None) -> DTO
```

**Purpose:** Define the backend integration boundary for reviewed answers; currently not implemented.

**Inputs:** user: authenticated User; question: 1-2000 characters; scope: {type: lease|portfolio, id: lease ID|null}; asOf: real ISO calendar date; threadId: optional owned conversation ID or None. HTTP validates scope shape and portfolio role; implementation must authorize records/thread before retrieval.

**Output:** Future result: Answer DTO with id, threadId, answer, status, citations, calculations, activity and compliance. Currently never returns a fabricated answer.

**Exceptions:** Currently always APIError 503 BACKEND_NOT_IMPLEMENTED. Future implementation must use 404 for invisible threads/leases and needs_clarification for insufficient evidence; HTTP may reject invalid input with 422 or permissions with 403.

## `post_requests`

```python
post_requests(self, *, user: DTO, leaseId: str, category: str, subject: str, message: str) -> DTO
```

**Purpose:** Persist a tenant clarification request for an owned lease.

**Inputs:** user: authenticated tenant with requests:create; leaseId: owned lease ID; category: string; subject: nonblank 1-120 characters; message: nonblank 1-5000 characters.

**Output:** Request DTO with generated ID, server tenantId, leaseId, trimmed subject/message, status=open, UTC createdAt and reply=None.

**Exceptions:** APIError 422 VALIDATION_ERROR for invalid/blank content; 401/403 for principal/role/permission; 404 NOT_FOUND for missing/invisible lease; sqlite3.Error.

## `post_requests_id_reply`

```python
post_requests_id_reply(self, *, user: DTO, id: str, reply: str) -> DTO
```

**Purpose:** Save a landlord reply to an organization-owned request.

**Inputs:** user: authenticated landlord with requests:write; id: opaque request ID; reply: nonblank 1-5000 characters. Repeated replies replace the current reply; threaded history is a backend TODO.

**Output:** Updated Request DTO with trimmed reply and status=answered; updates one row inside a transaction.

**Exceptions:** APIError 422 VALIDATION_ERROR for reply; 401/403 for principal/permission; 404 NOT_FOUND for missing/foreign request; sqlite3.Error.

## `post_policies`

```python
post_policies(self, *, user: DTO, file: bytes, filename: str, content_type: str,
                      state: str, effectiveFrom: str, familyId: str | None = None,
                      expectedVersion: int | None = None, title: str | None = None,
                      category: str | None = None, propertyId: str | None = None) -> DTO
```

**Purpose:** Store PDF bytes privately and append version metadata in a single serialized transaction.

**Inputs:** user: authenticated landlord with policies:write; file: PDF bytes, nonempty and <=10 MiB; filename: untrusted .pdf display name; content_type: application/pdf or application/octet-stream; state: NC; effectiveFrom: real calendar date. New family: title and category required, optional propertyId. Existing family: familyId and expectedVersion required; title/category/propertyId/state must agree if supplied. Effective date must be >= business today and strictly later than latest version start. Inherits immutable family timezone.

**Output:** PolicyVersion DTO with generated revision/family UUIDs, version, interval, supersedesId, upload timestamp, safe basename, byte size, SHA-256 contentHash, status=uploaded, pageCount/excerpt=None and compliance=pending. PDF bytes remain a SQLite BLOB; previous effectiveTo becomes new start atomically. This method does not parse, scan, index, review or mark a file ready.

**Exceptions:** APIError 401/403 for account/permission; 404 NOT_FOUND for missing/foreign property/family; 409 VERSION_CONFLICT for stale expectedVersion or invalid chronological append; 413 INVALID_FILE_SIZE for oversize; 422 for empty file, invalid PDF header/type/name, schema/date/state or changed family fields; sqlite3.Error. All transaction failures roll back.

## `delete_policies_id`

```python
delete_policies_id(self, *, user: DTO, id: str) -> DTO
```

**Purpose:** Cancel the latest future non-ready policy revision without erasing its audit evidence.

**Inputs:** user: authenticated landlord with policies:write; id: opaque policy revision ID. Cancellation is allowed only when effectiveFrom > business today, status != ready, and no successor exists.

**Output:** Deleted DTO {deleted: True}. Restores predecessor effectiveTo=None, records canceled metadata/PDF bytes in private policy_audit, then removes the revision from the active policy list atomically. A later cancellation retry returns 404.

**Exceptions:** APIError 401/403 for account/permission; 404 NOT_FOUND for missing/foreign revision; 409 VERSION_CONFLICT for effective/ready/nonlatest revision; 503 DATA_INTEGRITY_ERROR for missing predecessor; sqlite3.Error. Rollback preserves original history on failure.

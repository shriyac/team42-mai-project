# Phase 5B — authenticated backend-to-agent integration

## Implemented boundary

`BackendAPI.post_assistant_messages(self, *, user, question, scope, asOf,
threadId=None)` retains its public signature and now invokes the existing
`agent.graph.run_laga_agent()` through a thin integration layer.

Before generation, the method:
1. Re-reads the authoritative account and organization through `_principal()`.
2. Validates `AskInput` using the existing OpenAPI validator.
3. Restricts chat to tenants with `lease:read` and lease scope.
4. Authorizes the selected lease through `_lease()`.
5. Checks any supplied thread against user, organization, lease, and session.
6. Passes only the authoritative user ID/name and authorized lease ID to the
   graph. Browser text cannot change the retrieval scope.

The SQLite connection is closed before retrieval/generation. No SQLite schema,
account/session logic, CSRF validation, cookie settings, or existing principal/
lease authorization implementation was rewritten.

The HTTP handler still authenticates the session and checks Origin/CSRF first.
Only its assistant dispatch adds a per-call ContextVar binding using a hash of
the authenticated session cookie. The binding is reset in `finally`, including
on exceptions and thread-pool reuse. No token is saved in the thread registry.

## Retrieval and production behavior

`BackendAPI(..., assistant_retriever_factory=factory)` is a server-only
dependency injection seam. The factory has the existing graph interface:

```python
factory(tenant_id, tenant_name, lease_id) -> retriever
retriever.invoke(query) -> sequence_of_documents
```

Tests explicitly inject `MockLeaseRetrieverFactory` with synthetic evidence.
The production/default constructor has **no factory**. An authorized request
therefore returns **503 `RAG_UNAVAILABLE`**, before calling the agent. It does
not use the graph's empty-mock default or fictional bootstrap clauses.

An additional wrapper limits evidence to `Lease.documents` and checks metadata
tenant/lease ownership and, when present, organization ownership. It snapshots
the actual source citation metadata for final response validation. A broken
retriever returning another tenant's chunks, an unlisted document ID, or
foreign-organization metadata cannot supply answer evidence.

Monica's RAG module is still absent and was not invented or changed.

## Answer adaptation

`src/laga/assistant_adapter.py` maps the independent result to the existing
Answer schema, then the backend validates it against `contracts/openapi.json`.
The HTTP layer also performs its existing wrapped response validation.

- `passed` maps to `supported`; `abstained` maps to `needs_clarification`.
  Pending/failed/unknown validation and malformed results produce safe 503
  errors, never supported answers.
- Source ID, document ID, title, clause/section, page number, and literal
  excerpt are preserved. Where available, the section title is retained
  alongside the clause ID.
- Citations must match the snapshotted authorized retrieved evidence, including
  quote, page and section metadata. Citation markers must match the answer.
- Monetary units were verified from the UI contract/docs: public Calculation
  `result` is integer USD cents; the existing calculator emits USD dollar
  strings per monthly rental installment.
- Each calculation is replay-checked using the unchanged deterministic
  calculator, including its exact input/result schema and monetary units.
  Only then is its fee converted with Decimal to integer cents. Tampered
  amounts, unknown units, or incompatible results are rejected.
- A failed validation never publishes a numeric fee. A null/clarification
  calculator result is not replaced by a statutory-cap default.
- `tool_activity` maps to `activity`.
- Compliance is always `{"status": "unavailable"}`. No legal approval is
  fabricated.
- The backend returns the bare Answer; the existing HTTP layer supplies
  `{"data": answer}`.

## Threads and session isolation

Threads are opaque UUID ownership handles in a locked, expiring, bounded
in-memory registry. They are bound to:

`(organization_id, user_id, lease_id, authenticated_session_hash)`.

Another tenant, another lease, another session for the same tenant, a new
login after session rotation, or an unknown thread receives the same 404.
Internal service calls have a separate namespace and cannot adopt HTTP
session-bound threads.

The lifetime is at most the service's configured session lifetime; expired
entries are pruned. At 10,000 active handles, new conversations fail with 429.
Only successful, schema-valid responses register a new handle.

**Intentional MVP limit:** no transcript or conversation memory is persisted.
A backend restart invalidates handles. Multiple backend workers/replicas need
shared ownership storage or explicit session affinity before reliable thread
continuation across replicas. This is not a durable chat-history implementation.

## Documented errors

| Situation | HTTP / code |
| --- | --- |
| Missing/expired session | 401 `UNAUTHENTICATED` |
| Existing Origin/CSRF checks fail | 403 `ORIGIN_FORBIDDEN` / `CSRF_INVALID` |
| Non-tenant lease chat or missing lease permission | 403 `FORBIDDEN` |
| Portfolio request reaching the assistant service | 422 `UNSUPPORTED_SCOPE` |
| Tenant portfolio request blocked by existing HTTP guard | 403 `FORBIDDEN` |
| Malformed scope, date, or other AskInput | 422 `VALIDATION_ERROR` |
| Invisible/missing lease or foreign/unknown thread | 404 `NOT_FOUND` |
| No retriever or no authorized lease document IDs | 503 `RAG_UNAVAILABLE` |
| Unexpected graph failure | 503 `ASSISTANT_UNAVAILABLE` |
| Invalid graph result, citations, calculation, or public DTO | 503 `BACKEND_CONTRACT_ERROR` |
| Thread registry at capacity | 429 `ASSISTANT_BUSY` |

No provider exception text, source paths, or foreign evidence is included in
safe error responses. Retrieval failures handled by the graph can also return
a validated `needs_clarification` answer with no citations or calculations.

## Changed files

Created:
- `src/laga/assistant_adapter.py`
- `src/laga/assistant_integration.py`
- `tests/test_assistant_integration.py`
- `docs/PHASE5B_INTEGRATION.md`

Modified:
- `src/laga/backend_api.py`: injection seam, authorized assistant call, removal
  of the temporary debug echo.
- `src/laga/api.py`: session-bound assistant dispatch only.
- `tests/test_api.py`: replaced three obsolete debug-echo expectations with the
  new tenant/portfolio behavior; retained existing gateway/security coverage.
- `.replit`: development `run` and workflow commands use existing uv extras.
  The copied pip-based preview command failed because managed Python had no
  pip. Deployment configuration remains unchanged.
- `replit.md`: documents the working preview command and unavailable retrieval.
- `.agents/memory/team-integration-ownership.md`: records user-defined MVP scope.

The existing agent, calculator, calculator tests, frontend, OpenAPI schema,
bootstrap/compliance logic, dependency manifest, and dependency lock were not
changed. Fifteen protected files were checksum-verified. AST comparison also
confirmed unchanged authentication, principal/lease helpers, storage methods,
and initialization SQL. No commit, push, or branch merge was performed.

## Actual verification

```sh
uv run --extra api --extra test python -m pytest -q
npm test
npm run build
```

- **139 Python tests passed**, plus **57 subtests passed**.
- **42 frontend tests passed**.
- **0 failed, 0 skipped** in both suites.
- One third-party Starlette/AnyIO deprecation warning.
- Production frontend build succeeded.
- All original 15 calculator tests and 47 pre-backend-import tests remain
  included and passing.
- Thirty-three new integration/security test cases cover authorized graph
  calls; invisible leases/organizations; invalid IDs, sessions, Origin and
  CSRF; identity spoofing; real deterministic fee execution and cent conversion;
  missing terms and unsupported questions; invalid units/tampered results;
  citation provenance and tenant isolation; safe failures; thread ownership,
  lease binding, expiry/capacity, session rotation, and concurrent isolation.
- Positive and negative HTTP responses were validated against the existing
  OpenAPI schemas.
- The development workflow was restarted once after the preview-command fix;
  Vite and Python API started cleanly on ports 5000 and 8001.
- The login page was screenshot-verified without browser errors. The signed-in
  UI was not browser-tested; authenticated flows were exercised with HTTP
  integration tests and the existing real frontend gateway regression.
- Startup used the existing fictional-data bootstrap unchanged. Generated
  local SQLite/credentials remain ignored; no bootstrap password was inspected
  or published.

## Live Pinecone readiness and remaining blockers

The authenticated integration seam is ready for the next integration phase,
but this is **not a live-Pinecone-ready deployment**.

1. Supply the actual RAG implementation, its dependencies, and required service
   configuration; there is no production factory yet.
2. Verify the backend lease-document IDs against actual Pinecone document IDs.
   A server-side mapping/adapter must preserve the allowlist and enrich missing
   tenant/lease metadata only after checking authorized membership.
3. Exercise the actual retriever's filters, source spans, and optional answer
   generator. The unchanged graph deliberately permits only strict extractive
   grounding and conservatively clarifies unsupported contractual fee wording.
4. For standalone wheel/API-kit distribution, include the existing root-level
   `agent` and `tools` packages; the current upstream package discovery targets
   `src`. Source-checkout operation is tested; portable integrated packaging
   has not been completed.
5. Decide whether shared, durable thread ownership/history is needed for
   multi-worker production. Current handles are intentionally process-local.
6. Legal compliance review and historical document-version resolution remain
   unavailable; neither is implied by successful retrieval or calculation.

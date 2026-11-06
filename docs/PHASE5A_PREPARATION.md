# Phase 5A — workspace preparation and backend contracts

## Provenance and preservation

- Destination branch: `main`; initially clean and seven commits ahead of
  `origin/main`.
- Source: fetched `origin/feature/ui` at
  `36e2215a08d34151df8bef6da61306018a2de510`.
- No checkout, branch merge, commit, push, or deletion was performed.
- Imported 147 new files unchanged: `src/laga/`, `contracts/`, `frontend/`,
  `scripts/`, the six upstream Python test files, supporting `docs/`, Node
  manifests/lockfile, Vite configuration, ignore/attributes files, and
  `replit.md`.
- The only destination conflicts were `pyproject.toml` and `.replit`.
  Their original and upstream versions were saved under
  `.local/phase5a/{originals,upstream}/` before reconciliation.
- `pyproject.toml` retains LangGraph, pytest, Python >=3.11, and
  `tool.uv.package = false`; it adds the upstream build configuration, API
  extras, HTTPX/PDF test extras, command declarations, and `src` package discovery.
- `.replit` retains the existing Python 3.13 module, Nix channel, and Agent
  setting while adding upstream Node/web, launch, port, deployment, and
  workflow settings. The upstream launch commands' explicit
  `.pythonlibs/lib/python3.11/site-packages` target is retained; this is a
  directory name and does not switch the current Python interpreter.
- `uv.lock` was synchronized with the combined extras.
- Existing `agent/`, `laga_agent/`, `tools/fee_calculator.py`, existing tests,
  root `README.md`, and local project memory were not replaced. Upstream
  `.agents/` memory was deliberately excluded.
- Original Python source/test checksums and the imported-file manifest are in
  `.local/phase5a/`. All 147 imported files were verified against their source
  hashes after testing. No imported authentication, SQLite, backend, frontend,
  script, or test implementation was changed.

## Verified integration point

```python
BackendAPI.post_assistant_messages(
    self, *, user: DTO, question: str, scope: DTO, asOf: str,
    threadId: str | None = None,
) -> DTO
```

Location: `src/laga/backend_api.py`.

This method currently delegates to `_todo("post_assistant_messages", inputs=...)`.
For this operation, `_todo` returns a labeled temporary debug echo in an Answer
DTO, with `status="needs_clarification"`, no citations/calculations, and
`compliance={"status": "unavailable"}`. It performs no retrieval, model execution,
conversation persistence, or lease/thread authorization.

**No agent integration was added in Phase 5A.**

## HTTP request contract

The OpenAPI server prefix is `/api/v1`; the operation is
`POST /api/v1/assistant/messages`, operation ID `post_assistant_messages`.
`contracts/openapi.json` defines the request as `AskInput`:

```json
{
  "question": "Tenant question, 1–2000 characters",
  "scope": {"type": "lease", "id": "opaque-lease-id"},
  "asOf": "2026-11-04",
  "threadId": null
}
```

`question`, `scope`, and `asOf` are required. `threadId` is optional.
Scope type is `lease` or `portfolio`. A lease scope needs a nonblank ID;
a portfolio scope needs `id: null`. Extra request properties are rejected,
so client-supplied tenant IDs/names are not agent context.

`src/laga/api.py`:
- Resolves the `laga_session` cookie through `get_auth_session()`.
- Requires a signed-in user for this operation.
- Requires an allowed Origin and matching `X-CSRF-Token` for mutations.
- Restricts portfolio scope to landlords with `portfolio:read`.
- Validates input and calls the service with the authenticated `user` argument.
- Validates the returned Answer, then wraps it as `{"data": answer}`.
- Returns a safe 503 `BACKEND_CONTRACT_ERROR` on an incompatible service response.

These HTTP checks **do not establish ownership of a lease ID or thread ID**.

## Authoritative user and authorized lease representation

- A User DTO has `id`, `name`, `email`, `role`, and `permissions`.
  Roles are `tenant` and `landlord`; `leaseId` is an optional profile field,
  not an independent authorization grant.
- `BackendAPI._principal(db, user, ...)` re-reads the user by `user["id"]`,
  returning the authoritative profile and internal `organization_id`.
  Client-provided role, permissions, and organization are not trusted.
- A Lease DTO has an opaque `id`, `tenantId`, `tenantName`, `propertyId`,
  rent/deposit in integer USD cents, `dueDay`, dates/status fields, and optional
  `documents` containing document IDs.
- `_lease(db, organization_id, current_user, id)` selects within the authoritative
  organization. A tenant must also match `lease["tenantId"] == current_user["id"]`.
  Missing and invisible leases both return 404.
- `get_leases_id(user=..., id=...)` already uses `_principal`, role-appropriate
  `lease:read`/`leases:read` permission checks, and `_lease`; it returns
  `{lease, property, tenant, clauses}`.
- `get_workspace()` filters tenant leases by organization and tenant ID;
  landlords remain organization-scoped.

The later assistant implementation must reuse these existing authorization
boundaries **before retrieval**, not trust `scope.id` or a profile `leaseId`.
When a landlord asks about a lease, the agent's tenant name/ID must come from
that authorized lease's resident—not the landlord's own name/ID.
The current echo does not implement thread ownership or conversation storage;
those must not be assumed.

## Answer contract and required future adapter

The backend must return a bare Answer DTO containing:

`id`, `threadId`, `answer`, `status`, `citations`, `calculations`, `activity`,
and `compliance` (`demo` is optional).

| Independent Phase 3 result | Backend/UI contract |
| --- | --- |
| `validation_status`: `passed` / `abstained` | `status`: `supported` / `needs_clarification` |
| `tool_activity` | `activity`: `{label, status: complete|attention}` |
| Source citation `source_id` | Citation `id` |
| `document_id` | `documentId` |
| `clause_id` | `section` |
| `page_number` | `page` (integer or null) |
| `source_text` | `quote` |
| `document_title` | `title` |
| Calculator result schema with USD decimal strings | Calculation `{label, inputs, result, currency, method}`; `result` is integer USD cents |

A later adapter must create/resolve answer and owned thread IDs, map citations,
and convert valid calculator money to integer cents using Decimal. Calculation
`inputs` only allow integer/string/boolean values; raw nested result objects
cannot be inserted directly. A clarification result with a null fee must not
be converted to a fabricated numeric result.

Do not equate grounded retrieval or calculator success with legal compliance.
`compliance={"status": "unavailable"}` is valid; a `passed` review has additional
strict evidence/hash/date requirements. No compliance verdict was added.

The older `laga_agent/` interface is preserved but is not wired either.
The requested Phase 3 entry point remains `agent.run_laga_agent(...)`.

## Deferred integration boundaries

- `lease_rag/retrieval.py` is still absent; no RAG/Pinecone code or credentials
  were introduced.
- Resolve authorized `Lease.documents` IDs to actual RAG document IDs using a
  verified mapping. UI IDs must not be assumed identical to Pinecone IDs.
- Supply the scoped `.invoke(query)` retriever through the existing injected
  factory. The Phase 3 graph fails closed on missing tenant/lease metadata.
- The current graph supports one authorized lease, not portfolio orchestration.
- `as_of` is a reference date, not an inferred payment date or historical
  document-version resolver.
- The source setuptools discovery and upstream distribution scripts target
  `src/`; packaging the independent root-level agent/tools needs review before
  distributing an integrated wheel/API kit. No packaging behavior was rewritten.

## Actual verification

Dependency restoration and build:

```sh
uv sync --extra api --extra test
npm ci --include=dev
npm run build
```

All succeeded. `uv` notes that console entry points are not installed while
`tool.uv.package=false`; the supplied launchers run the source modules instead.

Test commands:

```sh
uv run --extra api --extra test python -m pytest -q
npm test
```

Results:
- Python: **106 passed, 0 failed, 0 skipped**, plus **57 subtests passed**.
  This includes all 47 pre-import agent/calculator tests.
- One third-party Starlette/AnyIO deprecation warning; no test failures.
- Frontend: **42 passed, 0 failed, 0 skipped**.
- Production frontend build succeeded.
- Startup regression tests exercised frontend/API launchers with isolated
  temporary databases, including session/CSRF and proxy behavior.
- Original source/test preservation and imported-file hashes passed.
- No persistent development workflow was started. The signed-in UI was not
  manually exercised. No live Pinecone, backend-agent wiring, or publishing
  was performed.

# Laga backend integration handoff

Contract version: **1.1.0** · OpenAPI **3.1.0** · Base path: **`/api/v1`**

## Start here

For the detailed printable handoff, see [the PDF integration handbook](Laga-Backend-Integration-Guide-v1.1.0.pdf). It includes all endpoint/model fields, worked requests/responses, hosting choices, review behavior and acceptance criteria.

Open `/api-docs/` for the interactive API Explorer. Read [BACKEND_CONNECTION.md](BACKEND_CONNECTION.md) for testing and same-origin/cross-origin connection instructions.

1. Import [openapi.json](../contracts/openapi.json) into an OpenAPI 3.1-compatible API tool, or use it to generate server models and endpoint stubs. This is the machine-readable source of truth.
2. Read [INTERFACE_CONTRACT.md](INTERFACE_CONTRACT.md) for authorization, policy timelines, concurrency, retrieval and state-law review requirements that schemas alone cannot enforce.
3. Use [examples.json](../contracts/examples.json) for complete response envelopes and [integration-examples.json](../contracts/integration-examples.json) for request examples and an illustrative passed-review response. All examples are fictional, not legal determinations.
4. Match [httpGateway.js](../frontend/src/services/httpGateway.js), the adapter already used by the UI. No component changes should be necessary to connect a conforming backend.

The spec describes the integration target. It does not mean these endpoints are deployed. The current application is a frontend prototype with an unconnected Python cache/review module.

## Endpoints

All paths below are relative to `/api/v1`. Successful responses use HTTP 200 and a JSON `{ "data": ... }` envelope, including uploads, logout and deletion.

| Method | Path | Purpose | Response schema |
| --- | --- | --- | --- |
| POST | `/auth/login` | Email/password login; server determines role | `Session` |
| GET | `/auth/session` | Current or anonymous session | `Session` |
| POST | `/auth/logout` | Invalidate session | `Logout` |
| GET | `/workspace` | Authorized portfolio or tenant projection | `Workspace` |
| POST | `/properties` | Register a property, including state | `Property` |
| GET | `/leases/{id}` | Lease, property, tenant and source clauses | `LeaseDetail` |
| POST | `/assistant/messages` | Ask using an authorized scope and reference date | `Answer` |
| POST | `/requests` | Tenant clarification request | `Request` |
| POST | `/requests/{id}/reply` | Landlord reply | `Request` |
| POST | `/policies` | PDF upload or new version; multipart form | `PolicyVersion` |
| DELETE | `/policies/{id}` | Cancel an eligible future staged version | `Deleted` |

## Transport

- Use cookie sessions and `credentials: include` (same-origin or appropriately configured cross-origin hosting); do not introduce a browser-stored bearer token. Production cookies must be Secure and HttpOnly. See the behavioral contract for CSRF and login protections.
- Return `csrfToken` in `Session`. Authenticated mutations require `X-CSRF-Token`.
- JSON requests use `Content-Type: application/json`. Let the browser set the multipart boundary for policy uploads.
- Anonymous `GET /auth/session` returns `{ "data": { "user": null, "csrfToken": null } }`.
- Errors use `{ "error": { "code": "VALIDATION_ERROR", "message": "Choose a valid state.", "requestId": "req-123", "fields": { "state": "NC is required." } } }`.
- Use the documented 400/401/403/404/409/413/422/429/500/503 responses. Do not return HTTP 204 or raw DTOs.
- Dates are `YYYY-MM-DD` calendar dates in the property/organization time zone. Timestamps carry a UTC offset. Money is integer cents.

## North Carolina requirements

Property registration and every policy upload require `state: "NC"`. A tenant does **not** submit a state: derive it from the tenant's authorized lease and property. Verify an upload's state against every property in its scope. A policy family retains its state, category and scope across versions.

`status` on a policy describes ingestion (`uploaded`, `processing`, `ready`, `failed`); `awaiting_backend` is mock-only. `compliance.status` independently describes legal review (`pending`, `passed`, `conflict`, `unavailable`). Ready ingestion alone does not authorize retrieval.

A passed review must identify the exact content hash, law revision, state, scope, reference date, check time, expiration and official citations. For answers, hash the exact UTF-8 `answer` string using SHA-256. For policies, return the immutable reviewed-content hash in `PolicyVersion.contentHash` as well as `compliance.contentHash`. The backend must define and persist the canonical extracted policy text whose bytes it hashes; do not substitute an excerpt or file hash. Preserve the original PDF checksum separately for audit.

Scope keys are `lease:<id>` and `portfolio:all` for answers, or `property:<id>` and `state:NC` for policy reviews. Exact scope/date matches and fresh reviews are required by the frontend. Validate calculations with the final answer before release. An absent, stale or mismatched review causes guidance to be withheld. Authorize the underlying objects independently of these keys.

Use [compliance.py](../src/laga/compliance.py) as the reusable source-cache/reviewer boundary, or implement equivalent behavior in your service. It shares official NC source snapshots between uploads and questions, refreshes daily and blocks on unavailable sources. It is **not** an HTTP server, PDF extractor or legal reasoning engine. Connect a qualified reviewer and assess amendments, effective dates, and applicable federal/local rules before approving content.

## Connect the frontend

Copy `frontend/.env.example` to `frontend/.env.local` and set:

```dotenv
VITE_LAGA_MODE=api
VITE_LAGA_API_BASE=/api/v1
```

Run your backend on `http://127.0.0.1:8001`; Vite proxies `/api` there. For a different local target, set `LAGA_API_PROXY` in the environment of the Vite process. Restart Vite after environment changes. `npm run dev` serves the UI at `http://localhost:5174`.

In production, route `/api` to your backend under the UI's origin, or use a full API URL with credentialed CORS and compatible cookies as described in the connection guide. The included static server returns 503 for API paths and is not a backend. API failures never fall back to demo data. Do not put service secrets in `VITE_*` variables.

## Acceptance before integration sign-off

Run `npm test` (PowerShell users may need `npm.cmd test`) for adapter/schema compatibility and `python -m unittest discover -s tests -v` for the cache/review boundary. Add backend endpoint tests against this spec; current frontend tests do not exercise your service.

Verify both tenant and landlord flows in API mode, especially cross-tenant/organization isolation, session expiry, CSRF, NC property registration, upload state mismatch, concurrent versions, effective-date boundaries, cancellation, blocked legal guidance, and exact answer-review hashes. Pending ingestion or review must never revive an expired predecessor.

Refresh status through `GET /workspace`. Job polling, retries, PDF download endpoints, streaming, pagination, and separate law-cache/review endpoints are not specified yet; coordinate any additions before changing the frontend contract.

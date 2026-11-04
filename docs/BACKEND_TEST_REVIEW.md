# Backend API three-loop review

Historical review date: November 1, 2026. The empty-application-start assumption in this report has since been superseded by [automatic bootstrap](BOOTSTRAP.md). Direct BackendAPI constructor tests still intentionally create empty stores. Scope: BackendAPI, HTTP parsing/validation, local SQLite initialization, UI gateway compatibility and the existing compliance boundary. Tests use isolated temporary databases; no developer account or business database is seeded by this review.

| Loop | Coverage | Findings fixed | Verified result after fixes |
| --- | --- | --- | --- |
| 1 - happy path and fresh install | Account/login/session/logout, property/workspace, lease/request/reply, policy append/cancel, real JavaScript gateway calls, independent local installations and restart persistence | Provisioning accepted unusable email and blank identity values. Default relative database path could select different files from different launch directories. | 22 Python tests passed |
| 2 - boundaries and types | Integer/bool/string/decimal inputs, property limits 1 and 10000, blank chat fields, duplicate JSON keys, lease cent/day values and no-write rejection | Enforced actual integer types and JavaScript-safe ranges, rejected duplicate keys and blank chat/scope text, checked dueDay 1-31 and nonnegative noticeDays before importing leases. Active portfolio rent cannot overflow the UI integer range. | 26 Python tests passed |
| 3 - extreme inputs and final regression | Invalid Unicode/control characters, valid Unicode/emoji, JSON depths 70/1500, NaN/Infinity, oversized JSON, 5000-digit multipart versions, exact 10 MiB PDF, future-ready cancellation refusal, invalid constructor values, concurrent legacy initialization and launch-directory independence | Reject malformed text before database writes; reject invalid/nonfinite/deep JSON and huge version conversions with actionable errors; validate session lifetime/path configuration before database creation; serialize additive membership migration. | Final 33 Python tests and 36 frontend tests passed |

## Important fixes

Invalid surrogate text previously reached property persistence before UTF-8 response rendering failed. Shared value validation now rejects that text before the mutation. Rejected Unicode, duplicate-field, type and lease-boundary cases assert that no records were persisted.

The default database is anchored to `<source-checkout>/data/backend.sqlite3`, and explicit paths are resolved when a BackendAPI instance is created. Starting the same checkout from another directory therefore keeps the same default file. Distinct developer checkout/database paths remain independent. Tests cover four concurrent initializers against a legacy account table; the membership column is added once without a duplicate-column race.

JSON integer validation rejects booleans, numeric strings and decimal-form numbers for integer fields. Every integer must fit within JavaScript's exact range, plus domain limits such as nonnegative rent/deposit. JSON nesting is limited to 64; bodies to 64 KiB. Nonfinite literals and duplicate JSON keys return 400. Schema/type/text errors return 422. PDF uploads accept exactly 10 MiB and reject larger files; total multipart body overhead remains bounded. Header checks do not certify PDF parsing, malware safety, extraction or indexing.

## First-execution database scope

The first local backend execution creates directories, the SQLite file, empty tables and indexes. It does not seed accounts, credentials, properties or synthetic lease data. Provision local accounts using the documented administrative command; create/import business data for that developer. Subsequent starts preserve existing records. Sharing a remote API or explicitly configuring the same file intentionally shares that backend's store; separate developer files do not synchronize.

The application store contains users/membership/password verifiers, hashed sessions/CSRF/expiry, login rate limits, properties, imported leases/citations, requests/replies, policy metadata/private PDF BLOBs and cancellation audit copies. It excludes chat transcripts, model credentials, extraction outputs and vector indices. Chat history is currently browser memory. The optional government-source LawCache has a separately configured SQLite path and is not started by this API.

## Chat trace

API mode: `Assistant` -> `main.jsx ask()` -> `httpGateway.ask()` -> `POST /api/v1/assistant/messages` -> `BackendAPI.post_assistant_messages(user=..., question=..., scope=..., asOf=..., threadId=...)`.

The request carries the session cookie and X-CSRF-Token plus question, scope, asOf and optional threadId. Valid input currently returns 503 BACKEND_NOT_IMPLEMENTED because retrieval/generation/review is still a backend TODO. No LLM API is called. In the default mock UI mode the mock gateway answers locally and no Python request is made.

## Reproduction

From an environment installed with `python -m pip install -e ".[api,test]"` and Node.js 22+:

```powershell
python -m unittest discover -s tests -v
npm.cmd test
```

Final result: 33/33 Python tests and 36/36 frontend tests passed; no failures or skips. The Python suite includes a live HTTP integration using the existing JavaScript gateway. The installed Starlette TestClient emits an upstream httpx deprecation warning; it does not affect these results. Deployment dependency locking remains an operational TODO.

No blocking implementation questions remain. Empty first-run storage and explicit local account provisioning are the assumptions used. Assistant services, PDF processing, payment reconciliation and production account/operational lifecycle work remain listed in [BACKEND_TODO.md](BACKEND_TODO.md). See [BACKEND_IMPLEMENTATION.md](BACKEND_IMPLEMENTATION.md) for local setup and database scope.

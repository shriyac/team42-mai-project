# Run and integrate the SQLite API

The local API now automatically bootstraps a fresh database. Follow [BOOTSTRAP.md](BOOTSTRAP.md) for the complete startup, sign-in and first-run behavior. Earlier empty-start assumptions are superseded for default application startup.

## One-command local runtime

After installing Node dependencies and the Python optional API dependencies in a virtual environment, run:

```powershell
npm.cmd run dev:local
```

The launcher detects `.venv`, starts the bootstrapped Python service on port 8001 and connects Vite on port 5174 in API mode. No manual provisioning, lease import, policy upload or `.env` edit is needed for the bundled development data. Sign-in credentials are generated in `data/backend-bootstrap-login.json`; the landlord email is `alex@alderliving.example`.

To run the backend independently use `python -m laga.api --insecure-local-cookie` for localhost HTTP. HTTPS deployments omit that option. Use `LAGA_BOOTSTRAP=0` or `--no-bootstrap` when an empty database is intentional. `npm run dev` remains the standalone UI command, whose default mode is mock; `dev:local` connects the real local API automatically.

## Implementation and contract

`src/laga/backend_api.py` is the business class; `src/laga/api.py` is its HTTP adapter; `src/laga/bootstrap.py` initializes the bundled data. All 11 published operations keep their OpenAPI operation IDs, route paths, keyword names and response DTOs. Startup checks signatures, requests and responses are validated, and business methods run in worker threads.

Implemented capabilities include local authentication/session management, workspace reads, NC properties, administrative lease import and authorized detail reads, tenant requests/landlord replies, private policy PDF storage, atomic policy append and future-revision cancellation with audit retention. [BACKEND_METHODS.md](BACKEND_METHODS.md) documents every method's purpose, inputs, outputs and exceptions. [BACKEND_TODO.md](BACKEND_TODO.md) covers external assistant, extraction/indexing and production integration work.

Bootstrap does not implement assistant generation or claim that PDFs have completed ingestion/review. Policies begin uploaded/pending. The bootstrap organization remains marked as fictional demo data in the UI.

## SQLite scope

The first application start creates each developer's own `<checkout>/data/backend.sqlite3`, its tables and bundled fictional records. Subsequent starts reuse the file, preserving edits and credentials. Separate developer files are independent and never synchronize. Two browsers using one API share that backend's store subject to authorization; multiple frontends pointed at a remote API share the remote database.

| Table | Purpose |
| --- | --- |
| users | Account profiles, internal organization membership, salts and scrypt verifiers |
| sessions | Token digests, user references, CSRF values and absolute expiry |
| login_attempts | Account/peer login rate-limit buckets |
| properties | Organization-owned property DTOs |
| leases | Tenant/property/unit associations, terms and clause citations |
| lease_documents | Private full lease PDF BLOBs and hashes |
| requests | Clarification requests and current reply |
| policies | PDF BLOBs, revision metadata, effective intervals and frozen timezone |
| policy_audit | Canceled metadata/PDF evidence |
| bootstrap_runs | Successful initialization version, organization and credential-file location |

The store excludes chat transcripts, provider credentials, vector indices and extraction outputs. Chat history is currently React memory. The optional LawCache in compliance.py uses a caller-configured SQLite path and is not started automatically.

The BackendAPI constructor creates schema only; create_app() performs default bootstrap. Injected test services are not seeded unless bootstrap=True is explicit. Existing populated databases are skipped to prevent mixing/overwriting data. Use a new custom database path if an existing manually populated developer database should remain intact.

## Configuration

- `LAGA_DATABASE`: SQLite path; default is anchored to the source checkout, independent of launch directory. Explicit relative paths resolve at construction.
- `LAGA_BOOTSTRAP`: default 1; set 0 for intentionally empty first-run storage.
- `LAGA_ALLOWED_ORIGINS`: exact comma-separated origins; defaults to localhost/127.0.0.1 on port 5174. Set the production UI origin explicitly.
- `LAGA_TIME_ZONE`: defaults to America/New_York for NC; each policy family freezes its timezone.
- `LAGA_COOKIE_SAMESITE`: lax by default; none requires Secure cookies.
- `LAGA_CONTRACT_PATH`: optional canonical OpenAPI location when relocating the source service.

The source-checkout/editable-install model requires contracts/openapi.json and bundled bootstrap/lease assets. Install with `python -m pip install -e ".[api,test]"`. Use `LAGA_PYTHON` to select an interpreter for dev:local, or `LAGA_LOCAL_API_PORT` for a different loopback API port.

Authentication uses normalized server-provisioned identities, salted scrypt verifiers, 8-hour absolute sessions, login rotation/revocation, HttpOnly cookies, CSRF and Origin checks, and persistent rolling 10-attempt/15-minute account/peer limits. No role or organization is accepted from login JSON. The CLI does not trust forwarded client headers; configure known proxies explicitly in deployment if peer-specific limiting is needed.

Additional accounts use `python -m laga.backend_api --database <path> --organization-id <internal-id> --profile <User-DTO.json>` with an interactive password prompt. New properties/policies and requests/replies use their existing UI/API routes; new leases use the trusted import_lease helper. No public user/lease creation route exists yet.

## Chat

API mode sends `POST /api/v1/assistant/messages` with the session cookie, X-CSRF-Token and `{question, scope, asOf, threadId}`. The HTTP adapter calls BackendAPI.post_assistant_messages with the authenticated user. The method currently returns 503 BACKEND_NOT_IMPLEMENTED; no LLM provider is called. Default standalone mock UI mode answers locally with no Python call.

## Validation and tests

Runtime guards supplement DTO shapes: actual integer types within JavaScript's exact range; nonnegative lease cents and valid due/notice days; no duplicate JSON keys, nonfinite numbers, invalid Unicode/control text or nesting beyond 64. JSON requests are limited to 64 KiB, PDFs to 10 MiB and multipart overhead to 256 KiB. Policy writes use serialized transactions and expectedVersion checks. Cancellation is restricted to the latest future non-ready revision and retains audit evidence.

```powershell
python -m unittest discover -s tests -v
npm.cmd test
npm.cmd run build
```

Python tests require Node.js 22+ for live JavaScript gateway integration and pypdf from the test extra for independent seeded-PDF validation. See BACKEND_TEST_REVIEW.md for the prior three-loop findings and BOOTSTRAP.md for current first-run behavior. Dependency locking, backups/retention, production account lifecycle and PDF/assistant workers remain backend operational work.

## Portable path references

Paths are relative to the current Laga root, independent of shell cwd. Bootstrap sign-in metadata now stores `database: data/backend.sqlite3` and `pathBase: Laga`; its SQLite marker uses a path relative to the database directory. Legacy absolute location fields migrate without changing account/password data. See [PORTABILITY.md](PORTABILITY.md) for relocation, Replit and artifact checks.

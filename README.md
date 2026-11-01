# Laga

A standalone React / JavaScript interface for the Lease Agreement Guard Agent. This project is unrelated to Monarch and has its own repository and runtime.

## Bootstrapped local application

After installing dependencies (`npm ci` and Python `pip install -e ".[api,test]"` in `.venv`), run `npm run dev:local`. This starts the Python API, automatically creates the fictional users/leases/policy PDFs in local SQLite and connects Vite in API mode. Sign in as `alex@alderliving.example` using the generated password in `data/backend-bootstrap-login.json`. No manual account provisioning or document upload is required. Choose Tenant login or Landlord login, then enter the account email and generated password. The same generated password initially applies to all 11 fictional bootstrap accounts on that installation; no credentials are pre-filled in the UI. The frontend-only mock preview does not authenticate bootstrap accounts. See [automatic bootstrap](docs/BOOTSTRAP.md) for full setup and restart behavior.

## Run locally

Requires Node.js 22 or later. From this directory:

```sh
npm ci
npm run dev
```

For account login, use `npm run dev:local` after installing Python API dependencies as described above. Choose Tenant login or Landlord login and enter the bootstrapped credentials. Plain `npm run dev` defaults to the frontend mock adapter and cannot authenticate accounts. All fonts and illustrations are served locally.

```sh
npm test
npm run build
npm start
```

`npm start` serves the built frontend on `PORT` or 5174. `vite preview` is for local verification only.

## Included

- Tenant home, structured lease details, source excerpts, questions with citations and clarification requests.
- Landlord overview, 12-unit inventory, 10 leases, filters, resident conversations and replies.
- Policy library for tenant, pet, utilities, waste, community and maintenance policies; new categories supported through Other.
- Current, scheduled and historical versions; explicit effective dates; immutable effective history; cancellation of a future staged version.
- Responsive navigation, keyboard search (Ctrl/Cmd K), accessible dialogs, loading/error/empty states and persistent dismissible feedback.
- Mock and HTTP adapters with a shared interface, schema tests and a Python API handoff contract.

## Policy dates

Versions use `[effectiveFrom, effectiveTo)` calendar-day intervals in the property/organization time zone. A replacement starts on its effective date and the predecessor stops immediately before that date. Future versions do not replace current ones early. An effective version that is not ready for retrieval blocks use of expired predecessors.

Preview date: October 30, 2026. Utilities v2 demonstrates a scheduled November 15 replacement. The Ask Laga reference-date field lets you explore either side of that boundary.

## Developer handoff

Start with [the backend integration handoff](docs/API_HANDOFF.md). Read [the interface contract](docs/INTERFACE_CONTRACT.md), [layer ownership](docs/TEAM_BOUNDARIES.md) and [OpenAPI 3.1](contracts/openapi.json). These are the implementation agreement for the future Python service. The original brief is preserved in docs/PROJECT_BRIEF.md; the user's React/JavaScript UI instruction supersedes its Streamlit suggestion.

Switch to the Python API by copying frontend/.env.example to frontend/.env.local and setting `VITE_LAGA_MODE=api`. Configure `VITE_LAGA_API_BASE=/api/v1`. For local development, `LAGA_API_PROXY` points Vite to Python (default http://127.0.0.1:8001). Production must route /api to Python through the same origin. The included static server intentionally returns 503 for API requests until replaced or fronted by that routing. There is no silent fallback to demo data.

## Replit

The Replit Run workflow installs Node/Python API dependencies and starts `npm run dev:local` on port 5000. Publishing builds the frontend in API mode and runs `node scripts/start-app.mjs`, serving the UI and Python API through one public port. The Python listener stays private.

Use [the Replit runbook](replit.md) for initial-password deployment secrets, allowed origins, source import and validation. The configured Autoscale deployment is for disposable fictional-data demonstrations: SQLite files on a published filesystem are not durable/shared storage. A persistent deployment requires durable storage integration. The source bundle excludes local databases and credentials. No live publishing was performed.

## Current limits

The reference backend implements authentication, sessions, authorization, SQLite persistence and fictional-document bootstrap. PDF ingestion, RAG, model calls, email and legal validation still require backend implementations; hosted durable/shared storage is not configured. Mock portfolio answers are deterministic examples. Lease and policy answers are withheld because legal validation is unavailable. Mock uploads stage metadata only and never pretend to ingest PDFs. Backend authorization is still mandatory; frontend role visibility is not a security boundary. Do not upload real tenant documents until the backend and access controls are ready.

## North Carolina jurisdiction and legal review

Property registration captures `state: NC`; tenants inherit state from the property associated with their lease and never select it. Each upload is tagged NC, including new versions. Property scope and state must match. The preview supports NC only and stages upload metadata without parsing the PDF. Ingested content without a passed legal review is excluded from policy retrieval.

`src/laga/compliance.py` provides a reusable SQLite government-source cache and a review boundary for the future Python API. The configured sources are the NC General Assembly's Chapter 42 and NC Department of Justice renting guidance. Fetches are shared across uploads and questions, cached for one day, and versioned by content hash. Expired sources that cannot refresh block review. Each policy and final answer needs a separate content-bound review; caching laws does not cache a compliance verdict for new content.

This module is not connected to an HTTP server, PDF extraction, or a legal reviewer. It does not certify compliance. The app visibly marks reviews pending/unavailable and withholds legal guidance. Integrating an authenticated server, a qualified review implementation, effective-date law history and federal/local coverage remains required before production use. A current snapshot cannot by itself establish historical or future law.

Run backend boundary tests with `python -m unittest discover -s tests -v`.

## Interactive API Explorer

Open [http://localhost:5174/api-docs/](http://localhost:5174/api-docs/) after `npm run dev`. The explorer uses the shared OpenAPI spec, accepts a local/proxied or full remote API URL, sends JSON and multipart requests with cookies/CSRF, validates response schemas and exports a test report. Its target is independent from the application's mock/API configuration.

See [backend connection instructions](docs/BACKEND_CONNECTION.md) for testing, local proxies, production reverse proxies, direct cross-origin hosting, CORS and cookies. Run `npm run api:kit` to build a shareable testing kit and refresh the API handoff archive. The static kit needs only Node.js 22+ to serve; no package installation is required to run its built UI.

## Detailed PDF integration handbook

Share [the backend integration PDF](docs/Laga-Backend-Integration-Guide-v1.1.0.pdf) and `laga-backend-documentation-v1.1.0.zip` with backend implementers. The PDF includes clickable navigation, all endpoint/model fields, request and response examples, same-origin/cross-origin deployment, NC review metadata and acceptance checks. It is generated from the repository's current contract, with its source checksum recorded in `docs/integration-guide-manifest.json`.

The generator is `node scripts/build-integration-guide.mjs`; the PDF renderer is `node scripts/print-integration-guide.mjs` using a local Chromium/Edge debugging endpoint (default 9224; override with `LAGA_DOCUMENT_BROWSER`). The renderer creates/closes its own temporary tab, validates page overflow/internal links and saves a tagged PDF with bookmarks. Generated examples are schema-tested with `npm test`.

State-law verification is disabled by default for both landlord and tenant experiences. Set `VITE_LAGA_STATE_VERIFICATION=true` in the build environment to enable review cards, policy review status and review-based answer/policy gating. Restart development or rebuild/redeploy production after changing it. When off, document processing, effective dates, state tagging and authorization remain enforced; answers carry no claim of legal verification. This public frontend flag does not disable a backend?s independent legal checks or start/stop its law-fetching jobs. Configure those separately in the backend; no flag is sent as a client-controlled permission bypass. The API contract and review metadata remain unchanged.

## Synthetic lease documents

The ten demo tenants now have searchable PDF lease packets in [docs/synthetic-leases](docs/synthetic-leases/README.md), with matching text, printable HTML, JSON extraction answer keys and a [manifest](docs/synthetic-leases/manifest.json). Each has household, income, contact, nonfunctional banking data and pet, smoking, waste and unit-specific annexures. Read the corpus README before ingestion; these are unsigned fictional fixtures, not legally validated lease forms. Build a handoff ZIP with `python scripts/package-synthetic-leases.py`.

## SQLite Python API

The UI now has a runnable Python API with one business implementation class, local login/session management, and SQLite-backed workspaces, properties, lease details, requests and policy versioning. Start with [backend setup](docs/BACKEND_IMPLEMENTATION.md), the [method reference](docs/BACKEND_METHODS.md), and [remaining integration work](docs/BACKEND_TODO.md). Assistant generation and document ingestion remain explicit backend tasks.

## Portable setup

All default application paths and persisted bootstrap location references are relative to the current Laga root or the configured data directory. Existing absolute location metadata migrates without reseeding accounts or resetting passwords. See `docs/PORTABILITY.md`; rerun `python scripts/check-portability.py --artifacts` after building handoffs.

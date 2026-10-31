# Laga

A standalone React / JavaScript interface for the Lease Agreement Guard Agent. This project is unrelated to Monarch and has its own repository and runtime.

## Run locally

Requires Node.js 22 or later. From this directory:

```sh
npm ci
npm run dev
```

Open http://localhost:5174. Choose Tenant and any of the 10 fictional residents, or Landlord for Alex Morgan's three-property portfolio. No password is needed in mock mode. Demo changes survive profile switches but reset when the page reloads. All fonts and illustrations are served locally.

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

The project includes a Node.js 22 Autoscale configuration and a production server that binds to `0.0.0.0`, respects `PORT` and serves both the app and API Explorer. The publishing build is `npm ci --include=dev && npm run build`; the run command is `node scripts/serve.mjs`. The configured internal port and `PORT` are both 5000, mapped to external port 80. The Replit Run workflow uses `npm run dev -- --port 5000`; local development still defaults to 5174.

Use [the Replit deployment runbook](replit.md) for import, build/publishing settings, frontend-only versus real API deployment, environment variables and smoke checks. Run `npm run check:deploy` before publishing. The generated `laga-replit-source-v0.1.0.zip` is a clean source import without local dependencies, credentials, uploads or browser data. This prepares the frontend demo/API Explorer; it does not deploy or implement the tenant backend.

## Current limits

This is a UI prototype. Real authentication/registration, database persistence, document storage, PDF parsing, ingestion, RAG, model calls, email and legal validation are not implemented. Mock portfolio answers are deterministic examples. Lease and policy answers are withheld because legal validation is unavailable. Mock uploads stage metadata only and never pretend to ingest PDFs. Backend authorization is still mandatory; frontend role visibility is not a security boundary. Do not upload real tenant documents until the backend and access controls are ready.

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

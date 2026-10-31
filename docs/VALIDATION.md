# Frontend validation record

Validated locally on October 30, 2026 with Node.js 24 and Microsoft Edge headless, using direct browser DevTools (no Playwright).

- `npm test`: 10 passing tests. Covers fixture totals, tenant isolation in the mock adapter, policy interval boundaries, invalid dates, overlapping versions, stale-update conflicts, future-version cancellation, unready-current-version fail-closed behavior, clarification requests/replies, HTTP cookies/CSRF/multipart mapping, and mock/example schema conformance.
- `npm run build`: successful Vite production build with local font assets.
- Browser: customer sign-in, home, source-grounded pet question, landlord sign-in, overview, properties, lease book, assistant, conversations, policy library, version history and upload dialog rendered without runtime exceptions.
- Browser: created a clarification request, switched to landlord, staged a new tenant-handbook revision effective November 2, and verified its scheduled/awaiting-ingestion presentation.
- Desktop 1440x1000: tested principal landlord pages for horizontal overflow; none found. Mobile 390x844: policy library and navigation checked; document scroll width equals viewport width.
- Production static server: home and SPA route return 200, missing assets return 404, disconnected /api routes return explicit JSON 503 rather than HTML or mock data.

Browser scripts are in scripts/browser-check.mjs and scripts/interaction-check.mjs. They require a local Edge DevTools session on 9224 and the development server on 5174; they are optional developer checks, not application integrations. Screenshots are local ignored artifacts under data/browser-check. Export handoff payloads with `node scripts/export-contract-examples.mjs`.

## Remaining work and limits

This is an interface prototype ready for backend integration and stakeholder review, not a production lease service. Python authentication, registration/account provisioning, database storage, private PDFs, asynchronous ingestion, real RAG/model calls, deterministic tool execution and email delivery are not implemented. Mock uploads preserve metadata only in browser memory. Real policy activation, immutable audit, tenant authorization and transaction constraints must be enforced by Python as described in INTERFACE_CONTRACT.md.

The current contract is optimized for small portfolios; pagination, bulk document upload, ingestion retries/progress, signed-document download, legal review workflows and operational monitoring need follow-up design before launch. Accessibility includes native dialog focus handling, keyboard navigation/search, visible focus, labels, reduced-motion handling and responsive navigation; a formal screen-reader audit and multi-browser production accessibility review remain outstanding. Replit configuration is supplied but has not been deployed or verified in a live Replit environment.


## Three-pass NC refinement ? October 31, 2026

1. Functional review: bound answer reviews to final text, state, reference date, authorized scope, current review interval and configured government citations. Added equivalent policy review identity/freshness checks. Reviewer expiration during assessment now blocks approval.
2. Experience review: introduced shared NC jurisdiction/source cards, document review steps, conflict/pending labels, immediate invalid-file feedback and clearer upload copy. Tenant jurisdiction is inherited; only landlords see state capture controls.
3. Browser and visual review: inspected desktop and 390px mobile screenshots; improved mobile action placement, status wrapping and typography. Exercised property registration, review dialog, PDF rejection, upload scheduling, tenant questions and cross-profile clarification requests. Screenshots are local ignored artifacts under `data/browser-check/`.

Run `node scripts/compliance-browser-check.mjs` with the local app on 5174 and a browser debugging endpoint on 9224. It checks registration, review steps, dialog Escape/focus restoration, invalid files, tenant state inheritance, withheld guidance, mobile overflow and browser runtime errors. `scripts/interaction-check.mjs` additionally checks navigation, clarification requests and scheduled version upload.

These checks verify prototype behavior and the cache/review boundary. They do not establish that a real lease complies with NC law; production ingestion and a qualified legal reviewer remain unconnected.


## API Explorer and backend connection

`/api-docs/` is a separate Vite entry that uses the canonical OpenAPI JSON directly. It also builds into `dist/api-docs/index.html`, which the included static server now serves as a directory index. Development proxy matching is restricted to `/api` and `/api/...` so it does not intercept `/api-docs/`.

Unit tests cover API-base normalization, encoded path IDs, JSON/multipart request validation, credentials/CSRF, response validation and unavailable/canceled connections. Browser QA uses `scripts/api-explorer-fixture.mjs` on 8002 and `scripts/api-explorer-browser-check.mjs` against a local browser debugging endpoint on 9224. The fixture is test-only, not a backend implementation. Verified flows include cross-origin session cookies, automatic CSRF capture, authenticated workspace retrieval, property mutation, binary PDF upload, invalid-response detection, target reset, report privacy and desktop/390px layouts. Screenshots are under ignored `data/browser-check/api-explorer-*.png`.

`npm run api:kit` builds and packages the interactive test kit and refreshed contract handoff. The kit contains built assets, docs and reference code; it does not contain a live backend or change the application's default mock mode.


## PDF handoff and compact UI

The generated integration handbook contains the 11 endpoint references, all 26 OpenAPI model field definitions and 8 schema-checked response examples. The PDF renderer verifies page count, page overflow and internal links, and produces a tagged PDF with an outline. The document manifest records the OpenAPI SHA-256 and PDF metadata. Source examples are checked by the frontend contract suite.

Developer Tools is now an in-flow control on login and home dashboards only; its reserved API Docs row keeps geometry stable when toggled. The separate preview label was removed from login, and the full product name appears on one line beside its logo. Browser checks cover toggle geometry, visibility across navigation and mobile overflow.

Ask Laga uses a viewport-sized desktop chat panel with an internally scrolling conversation and a visible composer. Mobile sources follow the chat. `scripts/ask-layout-browser-check.mjs` verifies composer visibility at 1440x900, 1280x720, 1024x768, 390x844 and 390x640, plus a long conversation. Browser QA does not emulate all real mobile keyboards or assistive-technology configurations.


## Replit deployment readiness review ? October 31, 2026

- `.replit` is now UTF-8 without BOM, selects Node.js 22, declares the Autoscale/cloudrun target, aligns PORT/localPort at 5174 and uses external port 80. Publishing installs build dependencies explicitly with `npm ci --include=dev` and launches Node directly.
- The production server checks build entries before listening, resolves dist relative to its own script, validates PORT, serves a frontend-only `/healthz`, handles HEAD/cache/media types and shuts down on termination signals. Unconnected API methods consistently return JSON 503; missing docs/assets never fall through to the SPA. Traversal, dotfile and symlink escapes are denied.
- Native-server tests cover startup, routes, headers, API errors, path handling and a CLI launched from an unrelated working directory with a custom PORT.
- A separate clean staging folder was installed from package-lock.json. Its tests, Vite build and emitted-asset smoke check passed using a temporary Node v22.23.4 runtime. The host is Windows; an actual Replit/Linux deployment was not performed.
- The npm advisory registry audit returned zero known vulnerabilities for the current lockfile. This is a point-in-time dependency check, not a guarantee against application vulnerabilities.
- `npm run check:deploy` is the repeatable built-artifact check. `scripts/package-replit.py` creates a source-only import archive and validates TOML/port consistency, expected files, archive integrity and source byte identity while excluding local credentials/dependencies/runtime data.

See `replit.md` for publishing settings, environment timing, real-backend options and post-publish verification. The frontend demo/API Explorer is deployable; tenant production auth/storage/ingestion/legal review still require the actual backend.

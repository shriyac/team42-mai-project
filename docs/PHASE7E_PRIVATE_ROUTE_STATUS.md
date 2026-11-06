# Phase 7E — private-route protection and verification status

## Blocked; preview stopped

The private-route fix and its focused tests passed, but full regression failed.
A bootstrap test inherited the real bootstrap environment secret and included
the password in an assertion failure. Do not repeat that value or use the fresh
demo environment for sharing. Replace it through secure secret entry and use
another fresh database before completing verification.

The workflow was stopped immediately after the failed regression results were
received; ports 5000 and 8001 were confirmed closed. No further verification,
commit, push, merge, publishing or Pinecone activation was performed.

## Confirmed root cause

A foreground, loopback-only Vite probe of `/data/backend.sqlite3` returned:

- HTTP 200, Content-Type `text/html`;
- an HTML doctype and Vite client marker;
- no SQLite header and no JSON response type.

Only these safe classification booleans were printed, not response contents.
This was Vite's SPA fallback, not actual SQLite bytes or a backend response.
The Python API is mounted separately under `/api/v1`; frontend routing and
backend authentication were not the source of this response.

## Changes made

- `scripts/private-routes.mjs`: shared path classification and Vite middleware.
  Rejects private root directories, filesystem URLs pointing at private paths,
  database files and sidecars, bootstrap credential filenames, dotenv files,
  key/certificate files, binding manifests and ingestion snapshots. Repeated
  decoding and slash normalization cover encoded and traversal variants.
- `vite.config.js`: installs the guard before Vite static handling/SPA fallback,
  retaining the existing filesystem deny protections and API proxy.
- `scripts/serve.mjs`: applies the same guard before production static lookup,
  API proxy dispatch and SPA fallback.
- `frontend/tests/previewSecurity.test.js`: replaces permissive private-path
  checks with explicit 403 assertions using raw HTTP paths, and exercises
  production serving, accidentally packaged canaries and symlink confinement.

No changes to frontend routing, authentication, SQLite implementation, the
agent, calculator or retrieval implementation were made. `.replit` is unchanged
in this phase; it retains the development-only fresh database setting.

## Actual results

### Focused security checks

`node --test frontend/tests/previewSecurity.test.js`:
**2 passed, 0 failed.**

The same tests also passed inside the full frontend suite. They exercised
ordinary, filesystem, encoded and traversal paths against ephemeral Vite and
the actual `createStaticServer` production implementation using a temporary
public root. Ordinary SPA routes, API documentation and frontend fixture
imports remained available.

These are not claims of a completed live HTTPS matrix or a production build
test using the real `dist` directory.

### Python regression

`PYTHONPATH=src:. uv run --extra api --extra test python -m pytest -q`:

- **255 passed, 2 failed; 57 subtests passed.**
- One existing Starlette/AnyIO deprecation warning.
- `test_installations_generate_distinct_passwords`: inherited the real
  `LAGA_BOOTSTRAP_PASSWORD`, so two installations had the same supplied
  password rather than independently generated passwords. Its assertion
  failure exposed the secret. Future suite invocations must not inherit real
  bootstrap secrets; random-generation tests need explicit environment isolation.
- `test_production_missing_build_fails_before_creating_database`: its isolated
  launcher fixture copies only the old two script files, omitting the new
  shared guard, so module resolution fails before the expected missing-build
  check. The fixture must include all launcher dependencies.

### Frontend regression

`npm test`: **41 passed, 3 failed** out of 44.

- Two existing production tests expect the previous 404/400 denial statuses;
  the new guard returns 403. This is a test contract mismatch, not evidence
  that the protected response body was served.
- The isolated production CLI fixture omits the new shared guard module.

The chained `npm run build` did not execute because `npm test` failed.

## Outstanding verification and Git review

- The real preview was restarted using the fresh database, but the live
  authentication/route matrix and browser reload checks were not run before
  the stop gate.
- No new phase-specific authentication success or deployment-readiness claim
  is made; prior phase results remain historical.
- The Phase 7B security commit is already an ancestor of this integration
  branch and requires no cherry-pick.
- Reviewed tracked-path checks found zero private runtime databases,
  bootstrap credential files, deployment bindings, actual document manifests
  or ingestion snapshots. The two approved public RAG PDFs are not private
  runtime data.
- No final comprehensive content scan or staged-release review was completed.
- The fix is **not ready to push as verified**.

Next work requires isolating test environments and updating fixture dependency
lists/status expectations, then securely replacing the exposed password and
bootstrapping another unused database. Only then resume the full live security,
authentication, browser reload, built-production and regression checks.

# Phase 7F — credential containment and completed verification

## Outcome

Replacement credentials were established through Replit Secrets and a new,
previously unused fictional installation:
`data/demo-phase7f/backend.sqlite3`. Preview is running against that database.
Maya remains `tenant-1` and owns `lease-1`.

The replacement password was checked inside an operational process for the
minimum 32-character requirement, bootstrap byte limit, and inequality with
both retired installation passwords. Values were not printed. Password
generation was delegated to the user's password manager through secure entry;
the agent did not generate or observe a password in chat.

Original databases and credential files remain offline for recovery; the
affected installation also has a private SQLite-aware recovery copy in
`data/retired-phase7f/`. Private directories use 0700 and created database/
recovery files were restricted to 0600. No password hashes were manually
edited. Do not restart an old installation: its retired password is still
valid there, not in the new environment.

## Root causes and fixes

### Secret inheritance and assertion diagnostics

`test_installations_generate_distinct_passwords` previously inherited the real
bootstrap secret. Two installations therefore received the same supplied
password, and unittest's failed equality assertion printed both operands.
Other tests and subprocesses could inherit provider keys and session secrets
as well. Explicit dotenv loading is another input route; merely deleting
environment keys would not isolate a real workspace `.env`.

The trusted `scripts/run-isolated-tests.mjs` launcher now:

- allowlists a small set of execution/certificate environment settings rather
  than enumerating every possible secret name;
- supplies a deterministic fictional bootstrap password and temporary database;
- omits real Pinecone, embedding, LLM, session and other inherited credentials;
- uses a temporary HOME and config/cache directories;
- disables automatic pytest plugin discovery;
- copies Git-listed source into a temporary tree, excluding private runtime
  files, actual dotenv files, bindings and snapshots;
- reuses installed package directories without copying runtime credentials;
- builds explicitly in API mode with the relative `/api/v1` base;
- cleans up its temporary tree after execution.

This is accidental-input isolation, not a security sandbox for malicious code:
installed dependency directories are shared. Never treat a marker environment
variable or source-copy mechanism as an adversarial isolation boundary.

`tests/conftest.py` rejects ordinary direct pytest collection outside this
runner. npm test entry points use the runner. Test password-generation coverage
uses deterministic fictional generator values and boolean assertions that do
not dump password operands.

New Node/Python deliberate-failure checks use fictional inherited sentinels;
neither failure output contains them. A second regression checks source
exclusions and absence of real demo recovery files/dotenv input in the copy.
No real credentials appeared in the isolated test output.

### Regression fixtures

Isolated Python and Node production-launcher fixtures now include
`private-routes.mjs`, a real dependency of `serve.mjs`.

Existing tests now expect the intentional 403 denial for dotenv, malformed
encoding and NUL requests rather than the old 400/404 statuses. Missing public
assets still require 404; private-path protection was not relaxed.

### Original private-route issue

The former HTTP 200 response was Vite's HTML SPA fallback, not a confirmed
SQLite disclosure. The shared guard remains before both Vite fallback and
production file lookup; frontend routing, backend authentication, SQLite logic,
agent, calculator and RAG algorithms are unchanged.

## Actual results

### Automated regression

Final `node scripts/run-isolated-tests.mjs all`:

| Check | Result |
| --- | --- |
| API-mode frontend production build | Passed |
| Full Python suite | 257 passed, 57 subtests passed |
| Full frontend suite | 46 passed, 0 failed |
| Focused isolation and route tests | 4 passed, 0 failed in focused run |

The four focused checks are included in the frontend count, not additional
unique tests. The Python suite includes authentication/session, bootstrap,
tenant-isolation and actual production-launcher coverage. One existing
Starlette/AnyIO deprecation warning remains.

A separate sanitized build was exported to the ignored workspace `dist`
directory for actual production-server checks. No real runtime secrets were
passed to that build.

### Real preview and production serving

- **150 real HTTPS private-route variants** ended in 403/404, covering original,
  retired and new database/credential paths, filesystem URLs, encoded/double
  encoded/traversal forms, dotenv, key files, manifests and snapshots.
- Replit's edge normalized **30 requests through same-origin redirects**
  before the final denial. The first hop is therefore not always 403/404.
  Redirect destinations were checked for HTTPS and the same hostname.
- The actual `createStaticServer` with the sanitized API-mode `dist` and
  loopback Python API denied **88 raw private-route variants directly with
  403**, while serving legitimate navigation, docs and health.
- Its API proxy passed Maya login, scoped workspace, foreign-lease denial,
  logout and session replay rejection.
- The first live harness treated an edge 307 as failure; the corrected check
  validated the same-origin redirect chain and final denial rather than
  ignoring the redirect or claiming its first hop was 403.

### Authentication and browser

- Both retired passwords returned 401 in the new environment.
- A genuine session minted only in the private retired-database recovery copy
  was anonymous at the new API and received 401 for workspace access.
  That test-created session was revoked afterward.
- Raw original pre-existing tokens were not recoverable from hashed storage;
  no claim is made of replaying an unavailable historical raw token.
- Real Chromium tenant login succeeded as Maya; workspace contained only
  `lease-1`.
- Her lease dialog loaded; foreign `lease-2` requests returned 404.
- Browser reload preserved the new session.
- Chat returned 503 `RAG_UNAVAILABLE`; no fabricated answer appeared.
- Sign-out invalidated workspace access; reload stayed logged out.
- Zero uncaught browser exceptions were observed. A public screenshot
  confirmed the logged-out login screen.
- The first browser harness selected an explicit ARIA role, but this UI uses a
  native `<dialog>`. Correcting the test selector to `dialog[open]` completed
  verification without changing UI code.
- Foreground browser and production-test processes were terminated and
  temporary profiles were removed. Only the managed preview workflow remains.

Startup and browser logs contained no critical application errors or newly
disclosed credentials. Expected 401/404/503 responses reflect security checks,
not startup failures.

## Files and operational configuration

Changes for containment and verification:

- `scripts/run-isolated-tests.mjs`
- `frontend/tests/testIsolation.test.js`
- `tests/conftest.py`
- `tests/test_bootstrap.py`
- `tests/test_replit.py`
- `frontend/tests/deployment.test.js`
- `package.json`
- `.replit`: development-only database path now points at the fresh installation.
- `replit.md`
- `.agents/memory/preview-file-security.md`
- this report

Phase 7E route guard/configuration/tests remain preserved. Tracked-path review
found zero private runtime database, credential, actual binding or snapshot
files; approved public RAG PDF fixtures were not classified as runtime data.
An exact-value scan of source/public build files against inherited credential
values and both retired bootstrap passwords found zero matches. Only the
match count was printed. `git diff --check` passed.
No old test-output credential value is reproduced in this report.

## Readiness and remaining limits

**Preview:** verified for the fictional UI/backend demonstration, with chat
explicitly unavailable rather than mocked.

**Production serving:** local configuration and build were exercised, not an
external published deployment. The existing disposable SQLite deployment is
not a durable/shared production tenant-data solution; see `replit.md`.

**Live RAG:** remains disabled. The actual ingestion snapshot and approved
bindings still need authoritative provision/approval. Development secret
existence checks show Pinecone, Nebius and Fireworks API keys absent. Passing
mock/unit tests does not authorize activation or prove live retrieval.

Retired passwords may remain in historical diagnostics; changing credentials
does not erase those records. Keep old installations offline and recovery
files private. The new password was not disclosed by this phase.

No agent-issued Git commit, push, merge, deployment, re-ingestion, Pinecone
write or activation was performed. Release/publishing actions require separate
authorization.

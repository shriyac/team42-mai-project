# Phase 7B — Replit demo verification

## Result

The current Replit preview is functional for the fictional tenant UI/backend
demo. Live assistant answers remain deliberately unavailable.

Verified starting branch: `integration/laga-mvp`, at
`f04edc2c2a214d6534721d3e7e965e62e5ba10b0`.
Inspected `.replit` and `replit.md`; used the existing `Start application`
workflow. No commits, pushes, merges, background task agents, Pinecone operations,
or deployment were performed.

## Security finding and local fix

Initial HTTP checks found that Vite's `/@fs/` route could serve the generated
SQLite database and bootstrap login JSON. Ordinary `/data/...` requests returned
the SPA, but this did not establish protection against direct filesystem routes.
No file contents or credentials were printed.

Stopped the workflow while adding explicit private-file deny rules in
`vite.config.js`, then restarted and verified the fix through the actual Replit
HTTPS URL. Existing Vite protections were retained. Root runtime data, uploads,
artifacts, private manifests/bindings, environment files, and local private
directories are denied without blocking frontend fictional fixtures.

Added `frontend/tests/previewSecurity.test.js` to exercise denial with a
temporary non-operational credential fixture. It also checks existing private
paths and that the UI and frontend fixture module still load. Missing private
paths may return the SPA; existing private paths must return 403.

**Before external sharing, rotate the fictional bootstrap account credentials
and invalidate existing sessions.** They were reachable before this local fix;
the checks cannot establish whether anyone else accessed them. Credentials were
not rotated in this verification request, and no authentication logic, SQLite
schema, or tenant data was rewritten.

The security fix is local and uncommitted; it is not yet on GitHub.

## Actual HTTPS browser checks

Used an isolated foreground headless Chromium process against the Replit
development HTTPS origin, with credentials read directly by the test process
from the existing generated bootstrap file. Browser/profile were cleaned up and
the test session was logged out.

| Check | Result |
| --- | --- |
| Tenant login through visible form | Maya Chen signed in successfully |
| Workspace | 200; only `lease-1` in the tenant lease registry |
| Lease detail API | `GET /api/v1/leases/lease-1` returned 200 |
| Lease UI | “My lease” opened Maya Chen / Unit 304, with lease summary |
| Foreign lease | `lease-2` returned 404 |
| Reload | Authenticated tenant session survived page reload |
| Cookie | Secure and HttpOnly flags verified without printing cookie values |
| Chat UI | Submitted question reached the backend and returned 503 |
| Chat contract | Explicit request confirmed `503 RAG_UNAVAILABLE` |
| Chat content | No assistant answer was rendered; no mock answer substituted |
| Private file routes after fix | SQLite, credentials, pending bindings, operator manifest all returned 403 |
| Logout | UI sign-out succeeded; session user became null |
| After logout | Workspace returned 401; reload stayed signed out |
| Browser runtime | No uncaught browser exceptions in the completed test |

The single public port is 5000, mapped externally to 80; the HTTPS preview
terminates TLS. Vite serves the UI and proxies same-origin `/api/v1` requests to
the Python server on private loopback port 8001. Login, cookies, CSRF-protected
requests, and logout were verified through this route, not just direct API calls.

## Regression checks and logs

- `npm test`: **43 passed**, including the new preview security test.
- `npm run build`: **successful**.
- `PYTHONPATH=src:. uv run --extra api --extra test python -m pytest -q tests/test_replit.py tests/test_portability.py`:
  **13 passed, plus 8 subtests**.
- One existing Starlette/AnyIO deprecation warning.
- `git diff --check`: passed.
- The previous full Python result of 257 tests plus 57 subtests was not rerun
  in full; this phase changed only Vite configuration and added a frontend test.

Initial test harness issues were corrected: the lease menu is “My lease,” not
“Your lease”; isolated Python tests need the explicit source import path; absent
`.env` files can return HTML rather than 403. These were test assumptions, not
authentication failures.

Startup logs show preserved fictional bootstrap, Python startup complete,
Vite ready, and successful authenticated API calls. No critical startup crash
or traceback was observed. Expected 503/404/401 responses correspond to disabled
RAG, isolation, and logout checks. Vite's deny warnings correspond to the
deliberate private-file probes. No credential values appeared in the inspected
startup logs.

## Demo and publishing boundaries

- Suitable now for demonstrating login, tenant workspace, lease viewing,
  session behavior, and safe unavailable-chat handling in this workspace.
- Not an end-to-end live RAG demo: actual ingestion snapshot, approved bindings,
  required ownership fields, secrets, and independent corpus checks remain
  prerequisites. No activation settings were changed.
- A published deployment was not exercised. Preview and publishing are separate
  installations; the preview-generated password must not be assumed to work in
  a fresh deployment.
- The configured publishing target uses local SQLite. Official Replit guidance
  says the published filesystem is not durable across redeployments; this
  configuration is for disposable fictional demos, not durable tenant records.
  No database migration or deployment configuration change was made.
- Before publishing/external sharing: rotate credentials, preserve the
  security fix through the separately approved Git workflow, and verify the
  deployed origin/bootstrap and login independently.

Reference: https://docs.replit.com/build/troubleshooting

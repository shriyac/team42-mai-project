# Phase 7D — fresh fictional demo environment

## Status: blocked at security verification

Fresh bootstrap succeeded, but the first private-file route check returned
HTTP 200 rather than the required 403 or 404. Following the explicit stop
instruction, testing stopped and the preview workflow was shut down.
Do not share externally or push this as a verified security release.

## Environment and preservation

- Branch: `integration/laga-mvp`.
- Preview-only `LAGA_DATABASE` is now
  `data/demo-phase7d/backend.sqlite3`, configured as a development environment
  variable rather than a repository default or deployment setting. The
  environment tool persisted this non-secret setting in `.replit` under
  `[userenv.development]`; that is the only `.replit` difference.
- The user supplied `LAGA_BOOTSTRAP_PASSWORD` through Replit Secrets. Its
  value was not printed. Process-local checks confirmed at least 32 characters,
  the bootstrap byte limit, and a value different from the old password.
  Password generation provenance was not independently verified.
- Existing first-run bootstrap created 11 fictional users, 3 properties,
  10 leases, 10 lease documents, 9 policies, and 4 requests.
- Maya Chen remains `tenant-1`; her lease remains `lease-1`.
- The original `data/backend.sqlite3` and bootstrap credential JSON were
  preserved. A SQLite-aware recovery copy and matching credential copy were
  placed in `data/retired-phase7d/`. Original file hashes were unchanged
  immediately after bootstrap.
- New and recovery directories have mode 0700; created database/recovery files
  were restricted to 0600. All these runtime paths are Git-ignored.
- No password hashes were manually edited. No existing account was reset.
- The old workflow was stopped before bootstrap. The preview was subsequently
  started against the fresh database for verification, then stopped again
  immediately after the failed route check.

## Actual verification results

Twelve checks passed through the real HTTPS preview/API before the route failure:

1. Old Maya password rejected with 401.
2. A valid session minted against the private, retired database copy was
   anonymous when presented to the new environment.
3. No original database session hashes were present in the new session store.
4. New Maya login succeeded as `tenant-1`.
5. Login cookie had Secure and HttpOnly attributes.
6. Maya's workspace contained only `lease-1`.
7. Own-lease request succeeded.
8. Foreign `lease-2` request returned 404.
9. A separate session HTTP request restored Maya's identity.
10. Disabled assistant retrieval returned 503.
11. Logout succeeded.
12. Replaying the logged-out session against workspace returned 401.

The session test used actual HTTP requests and cookies, not a browser reload.
No claim is made that browser UI reload behavior was verified in this phase.
The retired-copy test used a genuine session created only in that isolated
copy; raw pre-existing original session tokens were not available. Original
stored hashes were separately checked for absence from the fresh store.
The test-created retired-copy session was revoked during cleanup.

**Failed check:** `GET /data/backend.sqlite3` returned HTTP 200.
The gate required 403 or 404. The failure alone does not establish that SQLite
bytes were returned: an SPA fallback can also return 200. No successful
private-file protection claim is made from that response.

## Not executed after the stop gate

- Remaining old/new/recovery filesystem URLs.
- Encoded and traversal route matrix.
- Production static-serving security verification.
- Browser reload verification.
- Full Python suite, frontend suite, frontend production build, and security
  regression suite.

Earlier phase test counts are not fresh results for this environment.

## Git review and release status

The reviewed security commit
`bc4ef7b4bc1d90233c1fe1349fc6c51f011be113` is already an ancestor of the current
integration branch; it does not need cherry-picking. Its five changed files are:

- `vite.config.js`
- `frontend/tests/previewSecurity.test.js`
- `docs/PHASE7B_DEMO_READINESS.md`
- `.agents/memory/MEMORY.md`
- `.agents/memory/preview-file-security.md`

The commit's scope is the Vite private-file deny configuration, its regression
test, documentation and project security notes. It does not change backend
authentication, SQLite logic, the agent, calculator, or RAG algorithms.
The preview regression currently checks filesystem URLs but does not establish
the required explicit status for ordinary private URLs.

**Not ready to push as a verified security fix.** An explicitly authorized
follow-up must resolve the ordinary-route status failure, rerun the complete
private-route matrix against preview and production serving, verify browser
reload, then run all regressions and a final staged secret/file review.

Live Pinecone remains disabled. No indexes, retrieval activation, Git commits,
pushes, merges, or deployments were performed.

Tracked-file changes in this phase are the non-secret `.replit` development
setting and this status document. Application implementations were unchanged.

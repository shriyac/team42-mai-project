# Login validation: three rounds

Validated November 1, 2026 against the Python API and SQLite bootstrap, using Edge browser automation. Browser rounds used isolated temporary installations, with generated credentials read by the test process and never printed.

| Round | Cases | Result |
| --- | --- | --- |
| 1: happy path | Tenant and landlord sign-in, empty credential forms, back-navigation clearing, incorrect-password recovery, mobile layout | Passed |
| 2: negative cases | Required fields, malformed email, missing password, unknown email, wrong password, browser offline error, submit re-enabled after failure | Passed |
| 3: edge cases | Two synchronous form submissions, uppercase email, tenant credentials in landlord screen, session reload, logout and anonymous workspace rejection | Passed |

A separate bootstrap regression authenticates all 11 accounts with the installation password and checks each tenant has exactly their own lease. Backend API tests also cover invalid JSON/types, credential bounds, session rotation/expiry, CSRF, origins and login throttling.

## Fixes

- Added a synchronous submission guard so two submit events in the same render issue exactly one login request.
- Allowed the installed font package directory in the Vite development server, resolving it from the package location. This fixes font loading when dependencies are in a parent directory without embedding workstation paths. Confirmed the font returns HTTP 200.

## Re-running browser rounds

Start an isolated local installation with `LAGA_DATABASE` pointing to a fresh temporary SQLite file, then run `npm run dev:local`. Set `LAGA_LOCAL_UI_PORT` and `LAGA_LOCAL_API_PORT` if the default ports are in use.

Run `node scripts/login-browser-check.mjs` with these environment variables:

- `LAGA_LOGIN_TEST_URL`: UI URL (test script default: `http://localhost:5185/`).
- `LAGA_BROWSER_PORT`: running Chromium/Edge remote debugging port (default: `9224`).
- `LAGA_LOGIN_TEST_CREDENTIALS`: generated `backend-bootstrap-login.json` beside the temporary database.
- `LAGA_LOGIN_TEST_ROUND`: `1`, `2`, or `3`.

Use a fresh temporary installation for each round. The real API permits 10 attempts per account and peer within 15 minutes, including successful attempts. Testing every account rapidly through one browser correctly triggers throttling; the all-account unit regression uses separate peer identities. No rate-limit bypass was added to application code.

Run `npm test`, `npm run build`, and `python -m unittest discover -s tests` for regression coverage.

The role choice controls the login presentation. The authenticated account determines the actual role and permissions, including when the opposite role screen was selected.

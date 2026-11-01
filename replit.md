# Replit setup and publishing

The repository is configured for the API-backed UI: tenant/landlord login, automatic fictional-data bootstrap, and same-origin `/api/v1` routing. Import the complete Laga project root, including `src/`, `contracts/`, `docs/`, `frontend/`, scripts and lockfiles. Do not import local SQLite data, credentials, `.venv`, or `node_modules`.

## Preview

The Run button installs Node and Python API dependencies, then runs `npm run dev:local`. Python packages go into `.pythonlibs/lib/python3.11/site-packages` rather than the read-only Nix system Python; no virtual environment is needed. It starts Vite on public port 5000 and Python privately on loopback port 8001. Bootstrap creates 11 users, 10 leases and their PDFs, three properties, nine policy PDFs and four requests. No manual provisioning is needed.

Choose Tenant login or Landlord login and enter an account email and the password in `data/backend-bootstrap-login.json`. The optional `LAGA_BOOTSTRAP_PASSWORD` secret can supply the initial password instead; it must contain at least 24 characters and at most 1024 UTF-8 bytes. The same initial password applies to all fictional accounts. Existing accounts and passwords are preserved on restart.

## Publishing

The explicit build below owns dependency installation. `[packager.features].enabledForHosting = false` requests disabling the automatic publishing install, but publishing was observed to invoke `uv sync` anyway. Therefore `pyproject.toml` also sets `[tool.uv].package = false`, preventing that preliminary sync from building/installing the editable project into read-only Nix system Python. This uv-only setting does not disable the explicit pip installation or setuptools packaging.

The `.replit` build installs `.[api]` Python dependencies and builds the UI in API mode. Publishing runs `node scripts/start-app.mjs`, which starts Python privately, waits for its readiness, then serves the built frontend and proxies `/api` over the single public port. API Explorer remains available at `/api-docs/`. Production cookies retain Secure and HttpOnly; plain localhost development uses the HTTP cookie option, while Replit HTTPS Preview also uses Secure cookies.

Before publishing, configure deployment Secrets:

| Variable | Purpose |
| --- | --- |
| `LAGA_BOOTSTRAP_PASSWORD` | Choose the initial fictional-account password for a fresh deployment, since its generated credential file is separate from Preview. Never put it in a `VITE_*` variable. |
| `LAGA_ALLOWED_ORIGINS` | Exact HTTPS published origin, plus any custom domains, comma-separated. Recommended explicit setting. |
| `PORT` | Public listener; configured as 5000. |
| `VITE_LAGA_MODE` | Build-time setting: `api`, configured in `.replit`. |
| `VITE_LAGA_API_BASE` | Build-time setting: `/api/v1`, configured in `.replit`. |

When origins are not explicitly set, the backend derives them from `REPLIT_DEV_DOMAIN` and comma-separated `REPLIT_DOMAINS`, plus local development origins. Unknown origins remain rejected. Rebuild after changing frontend variables. Changing the bootstrap secret does not reset an existing database password.

### Storage scope

The current `cloudrun` configuration is suitable for disposable fictional-data demonstrations. Every fresh filesystem bootstraps its own SQLite database. Replit advises against relying on writes to a published app filesystem: changes, sessions and generated credentials can disappear or differ across instances. Do not use this configuration for durable tenant records. Durable/shared database and document storage must be integrated before that use; selecting a Reserved VM alone is not a persistence guarantee. See [Replit publishing documentation](https://docs.replit.com/learn/projects-and-artifacts/replit-deployments).

Preview and published deployments are separate installations. Preview's generated password is not automatically the published password. A deployment bootstrap secret makes the published initial password known without logging it. No credentials are served as public assets.

## Checks

The API constrains Starlette below 1.0 to retain compatibility with the existing httpx-based test client. Install the `test` extra before running the Python suite; the Run button only needs the `api` extra.

```sh
npm ci --include=dev
python -m pip install --target .pythonlibs/lib/python3.11/site-packages --upgrade ".[api,test]"
npm test
npm run check:deploy
python -m unittest discover -s tests
python scripts/package-replit.py
```

`check:deploy` checks build assets and the standalone static server. `tests/test_replit.py` separately verifies the production launcher, first-run bootstrap, published-origin login, secure cookies, workspace access and logout through the production proxy. Proxy regressions cover request bytes, CSRF, cookies, API Explorer routing and upstream failure. The launcher also offers `node scripts/start-app.mjs --check` for a temporary startup check; use an isolated database for this check.

After publishing, check `/`, `/api-docs/`, `/healthz`, and `/api/v1/auth/session`; then sign in, reload, open the workspace and sign out for both roles. `/healthz` covers the frontend listener; it does not certify ingestion, legal review or source availability. Policy ingestion and reviewed chat responses retain their existing backend implementation limits.

## Source bundle

`python scripts/package-replit.py` produces `laga-replit-source-v0.1.0.zip`, excluding runtime accounts, passwords, uploads and dependencies. Extract it into the Replit project root. If using Git import instead, newly created local source files must be committed/pushed first. This review has not published or pushed the application.

## Three-round readiness review (November 1, 2026)

1. Configuration/build/package: parsed Replit TOML, checked module/port/API-mode settings, built the production UI, ran frontend/deployment regressions, and rebuilt the source-only archive.
2. Preview: started a fresh SQLite installation from an unrelated launch directory with a simulated Replit HTTPS domain. Verified API-mode Vite, same-origin API routing, bootstrap login, Secure cookies, workspace access, logout and clean launcher completion. Relocation/origin tests passed.
3. Production and failures: verified both roles through the production proxy, tenant scope, session restoration, missing-CSRF and foreign-origin rejection, logout/replay protection, invalid/colliding ports, missing Python, missing build output and an occupied public port. Existing proxy tests cover multipart bytes, upstream failure and forwarded-IP spoof protection.

Fixed Preview Secure cookies, strict port parsing, equal public/API port rejection, and nonzero failure status when a child exits unexpectedly. These checks simulate Replit runtime settings locally; the application has not been published or tested on a live Replit deployment. Filesystem durability remains the storage limitation described above.

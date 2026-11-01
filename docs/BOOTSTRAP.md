# Automatic local bootstrap

Application startup now initializes each fresh local SQLite database with the bundled fictional dataset. No user-provisioning call, lease import, property registration or policy upload is required to get the development workspace populated. This supersedes the earlier empty-first-run setup.

## Start

Install dependencies once using the normal checkout setup, then run:

```powershell
npm ci
python -m venv .venv
.venv/Scripts/python.exe -m pip install -e ".[api,test]"
npm.cmd run dev:local
```

On macOS/Linux use `.venv/bin/python` for the installation command. The launcher detects the local virtual environment automatically; `LAGA_PYTHON` can select another interpreter. It starts the Python API on 127.0.0.1:8001, waits for readiness and starts Vite in API mode on localhost:5174. It sets the proxy/API mode itself; no `.env` edit is needed. Ctrl+C stops both child services. `LAGA_LOCAL_API_PORT` can choose a different loopback API port, and `LAGA_LOCAL_UI_PORT` changes the UI port. For a nondefault UI port also set LAGA_ALLOWED_ORIGINS to that exact UI origin. `npm run dev:local -- --check` verifies both services start in API mode, then stops them.

The one-command launcher is available in the full source checkout; backend-only handoff archives use the API-only command and a separately hosted UI.

For API-only startup use `python -m laga.api --insecure-local-cookie` from an installed environment. HTTPS deployments omit that local HTTP cookie option. Calling the default `create_app()` factory also bootstraps. A deliberately injected BackendAPI instance is left alone unless `create_app(service, bootstrap=True)` is requested, so tests/integrations retain control over their databases.

## What is created

| Data | Count | Notes |
| --- | --- | --- |
| Accounts | 11 | Alex Morgan landlord and all ten named fictional tenants |
| Properties | 3 | Willow House, The Juniper and Cedar Court; 12 units |
| Leases | 10 | Existing IDs, tenant/property associations, terms and source citations |
| Lease PDFs | 10 | Full checked-in synthetic packets, 12 pages each; hashes checked before import |
| Policy PDFs/revisions | 9 | All existing policy families/versions; generated native-text PDFs from their fictional policy text |
| Requests | 4 | Existing fictional resident requests and current reply |

The organization is `org-alder-demo`. The landlord email is **alex@alderliving.example**. Tenant emails match the UI fixtures, for example **maya@example.test**. All accounts in one installation share a newly generated random development password; different installations receive different passwords and independent SQLite files.

The password and account list are automatically saved beside the database, by default:

```text
data/backend-bootstrap-login.json
```

Open that local file to sign in; no account setup is required. Startup prints its path, never the password. The file is created with owner-only POSIX permissions where supported; on Windows it inherits the local directory's access controls. It is under ignored private `data/`, is not returned by HTTP, and is excluded from every handoff archive. Do not distribute an initialized data directory with the application. No public fixed default password is added to source or documentation.

## Restart and failure behavior

The bootstrap inserts all rows in one SQLite transaction guarded by BEGIN IMMEDIATE. A successful marker in `bootstrap_runs` means later starts skip seeding, preserving edited records, passwords and policy history. Concurrent starts serialize and only one seeds. Failure rolls back seeded rows and removes a newly created credential file; a later start can retry. An existing valid credential file from an interrupted attempt can be reused for the same database/account set.

Any already-populated database without a bootstrap marker is left unchanged; bootstrap never merges demo users into manually created accounts or resets existing credentials. If an earlier empty-start developer database already contains manual records, use `LAGA_DATABASE` to select a new file to try automatic bootstrap. No existing database is deleted by this feature.

For an intentionally empty deployment use `LAGA_BOOTSTRAP=0` or the CLI option `--no-bootstrap`. The BackendAPI constructor creates tables only; the application startup factory orchestrates the automatic data import. Each developer's default file is `<checkout>/data/backend.sqlite3`; custom database paths get a corresponding `<database-stem>-bootstrap-login.json` next to them.

## Documents and remaining integrations

Both lease PDFs and policy PDFs are stored as private SQLite BLOBs. `lease_documents` holds lease bytes and their hashes; `policies` holds policy bytes and version metadata. Policy historical/future effective dates and immutable scope are preserved by a trusted snapshot import, rather than passing historical fixtures through the public current-date upload API.

Seeded policy documents remain **uploaded**, with **pending** compliance, and no claimed extraction/index readiness. The new policy PDFs contain the actual bundled policy text with a clear synthetic notice; they do not pretend to have the mock metadata's original fictional page counts/file sizes. The UI marks the seeded organization as demo data. This initialization does not implement document ingestion, legal review or model-backed chat. The assistant API still returns BACKEND_NOT_IMPLEMENTED until connected.

Additional policies can be added through the existing UI or POST /api/v1/policies. Additional accounts can still be provisioned with the administrative CLI; additional leases use import_lease. No new public user-creation or lease-upload route is introduced by bootstrap. See BACKEND_METHODS.md for those administrative helpers.

## Maintenance

`contracts/bootstrap.json` is a committed deterministic snapshot of frontend fixture records, exported with:

```powershell
node scripts/export-bootstrap-fixtures.mjs
```

Runtime bootstrap does not need Node to parse fixture data, Chromium, pypdf or external network services. It needs the snapshot, canonical OpenAPI and synthetic lease manifest/PDFs, all included in the backend handoff ZIP. Regenerating the snapshot does not silently migrate existing initialized databases; future seed upgrades need an explicit migration design.

Tests cover snapshot alignment, independent random credentials, every seeded PDF, real login and tenant projection, restart preservation, concurrent initialization, malformed assets, transaction rollback before/after credential creation and explicit empty mode. Run the full Python and frontend suites after changing bootstrap data or behavior.

Observed validation: 42 Python tests and 37 frontend tests passed, and the production UI build succeeded. This checkout was bootstrapped with all counts above; generated credentials remain only in the local private data directory.

## Portable path references

Paths are relative to the current Laga root, independent of shell cwd. Bootstrap sign-in metadata now stores `database: data/backend.sqlite3` and `pathBase: Laga`; its SQLite marker uses a path relative to the database directory. Legacy absolute location fields migrate without changing account/password data. See [PORTABILITY.md](PORTABILITY.md) for relocation, Replit and artifact checks.

## Replit publishing password

Set the deployment secret `LAGA_BOOTSTRAP_PASSWORD` to at least 24 characters (at most 1024 UTF-8 bytes) to choose the initial fictional-account password on a fresh published installation. Without it a random password is generated. This secret is read only during initial creation, never resets existing users, and must never be placed in frontend variables or logs. Preview and publishing have separate databases. See [the Replit runbook](../replit.md) for same-origin routing and storage limits.

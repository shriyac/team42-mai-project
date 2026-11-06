# Laga portability review

All application paths are resolved from the current Laga project root, not a developer's checkout location or shell working directory. The root is discovered from the installed source module or script location; the containing folder may have any name and may contain spaces. No workstation-specific directory is required.

## Three verification loops

1. Source/runtime review: scanned application source, documentation and configuration; changed bootstrap location metadata to relative references; made relative DB/contract/cache configuration resolve from Laga; fixed the cwd-dependent contract exporter and Replit source-package assertion. The existing 42 Python tests passed.
2. Relocation review: seeded a copied Laga under another folder, made the original folder unavailable, then started the copy from an unrelated cwd. Sign-in and all 10 leases survived with the same password. Anonymous legacy Windows metadata migrated without changing account identities/password verifiers. Both JS exporters targeted their own copied project. Replit-style port/preview origin settings derive from environment variables.
3. Distribution review: rerun all regressions and deployment/build checks; scan source/runtime metadata, PDF text/metadata/links and rebuilt source/backend/testing archives. Run the reproducible checks below for the current recorded result.

## Relative path rules

| Item | Portable reference | Base |
| --- | --- | --- |
| Default SQLite file | data/backend.sqlite3 | Laga root |
| OpenAPI | contracts/openapi.json | Laga root |
| Bootstrap snapshot | contracts/bootstrap.json | Laga root |
| Lease manifest/PDFs | docs/synthetic-leases/... | Laga root |
| Default sign-in file | data/backend-bootstrap-login.json | Laga root |
| Credential JSON database field | data/backend.sqlite3, pathBase=Laga | Laga root |
| External custom data directory | backend.sqlite3, pathBase=credentialsDirectory | Beside sign-in file |
| SQLite bootstrap credentials_path | backend-bootstrap-login.json | Beside DB file |

Use forward slashes in persisted metadata. Runtime file operations still resolve paths on the current host, which is necessary to open files; those computed paths are not static workstation references. Relative LAGA_DATABASE, LAGA_CONTRACT_PATH, administrative --database, bootstrap fixture/document settings and LawCache paths all start from Laga, even when the process starts elsewhere. Explicit absolute configuration remains an optional operator override; do not hardcode such overrides into shared source.

Existing absolute bootstrap metadata is migrated automatically on startup. Only location fields change; account records, password verifiers, PDFs and application data remain intact. Credential-file updates use an adjacent private temporary file and atomic replacement. The credential-integrity verification remains in place before metadata migration. Password changes and new accounts are never introduced by this migration. Copy the entire initialized data directory if moving an existing installation; freshly installed developers get independent data and generated credentials.

Custom DB and credential locations must be on the same filesystem volume to express their relationship relatively. No runtime data or local environments are included in ZIP handoffs. Virtual environments, node_modules and editable-install metadata are machine-managed and must be recreated on a new workstation rather than copied.

## Replit

Import/extract the full source root, not frontend alone. Python modules and Node scripts discover that root wherever Replit places it. The source packager accepts the configured Python/web modules as well as requiring nodejs-22, and excludes runtime data, virtual environments, bytecode and editable-install metadata.

For a bootstrapped API/UI Preview after dependency installation, use `npm run dev:local`. The launcher uses LAGA_LOCAL_UI_PORT, otherwise PORT, otherwise 5174; Python's default Origin list uses that same port and the current REPLIT_DEV_DOMAIN when supplied. Explicit LAGA_ALLOWED_ORIGINS takes precedence. No developer-specific preview hostname is saved in source. Replit's supplied preview domain is described in its [configuration reference](https://docs.replit.com/references/project-setup/configuration).

The .replit Run and publishing configuration now start the API-backed UI. Preview uses the combined development launcher; publishing uses scripts/start-app.mjs with same-origin API proxying. See replit.md for bootstrap secrets, published origins and SQLite persistence limitations. No live deployment was performed.

## Reproducible checks

```powershell
python -m unittest discover -s tests -v
npm.cmd test
npm.cmd run check:deploy
python scripts/package-api-kit.py
python scripts/package-replit.py
python scripts/check-portability.py --artifacts
```

The artifact scanner uses pypdf from the test extra; the quick source/runtime check has no external dependencies. It reports file names and field locations, never credentials. It scans readable application files and document artifacts, not dependency implementations or historical Git objects. Generic web URLs and author names are not workstation filesystem paths. Existing generated PDFs are not regenerated solely to change line endings or provenance.

## Recorded results

The final verification passed 48 Python tests and 37 frontend tests. Production build/deployment smoke checks passed. The combined launcher passed with PORT and a simulated Replit preview domain, without manual origin overrides. Artifact scans passed for source/text files, runtime credential/SQLite location fields, all generated PDF text/metadata/links and rebuilt backend/API-testing/documentation/Replit source archives. Existing local account IDs and password verifiers were compared before/after the live metadata migration and remained unchanged. No actual Replit publishing was performed.

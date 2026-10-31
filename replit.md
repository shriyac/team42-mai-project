# Replit deployment runbook

Laga currently deploys as a **frontend demo plus API Explorer**, not a completed tenant-service backend. Use the repository root as the Replit project root. No publishing has been performed by this review.

## What is configured

- Node.js 22 through `.replit` (`modules = ["nodejs-22"]`). No Python or browser installation is needed to build or serve the frontend.
- Development Run: `npm run dev`, bound to `0.0.0.0:5174`.
- Autoscale publishing target: `cloudrun`.
- Publishing build: `npm ci --include=dev && npm run build`.
- Publishing run: `node scripts/serve.mjs` (a long-running production server, not Vite).
- One public port: internal `5174` mapped to external `80`; `PORT=5174` is the configured default.
- The production server respects `PORT`, binds to `0.0.0.0`, validates its build output before opening the port, and handles shutdown signals.
- `/healthz` reports only frontend-server readiness. It is not a check of the backend, legal reviewer, database or government sources.

## 1. Import the correct files

Import the repository root, or upload/extract `laga-replit-source-v0.1.0.zip` into the project root. Do not import only the `frontend/` directory. The build also imports `contracts/` and documentation assets outside that directory.

Required items include `.replit`, `package.json`, `package-lock.json`, `vite.config.js`, `frontend/`, `contracts/`, `scripts/serve.mjs` and the documentation PDF/connection guide. The source bundle includes the full relevant source and tests. It excludes local credentials, `.git/`, `node_modules/`, `dist/`, browser profiles, uploaded files and generated ZIP archives.

If importing through Git, commit/push the intended source first: untracked local files are not included by Git import. This workspace's review did not create a commit or push.

The pre-generated PDF at `docs/Laga-Backend-Integration-Guide-v1.1.0.pdf` is a build input for the API Explorer's download link. Keep it in the import. **Do not run the PDF renderer or `npm run api:kit` as a Replit deployment build command**; those are local document/packaging workflows and have additional tooling requirements.

## 2. Verify development Preview

In Replit's Shell, from the project root:

```sh
npm ci --include=dev
npm test
npm run check:deploy
```

Then select Run and open Preview. The commands must finish successfully before publishing. `--include=dev` is intentional: Vite and the explorer's schema compiler are build dependencies even if `NODE_ENV=production` is set. The lockfile includes the platform-specific Linux build packages; do not copy Windows `node_modules` into Replit.

`npm run check:deploy` rebuilds and starts a short-lived local smoke-test server. It checks built app/docs entries, all emitted assets, the PDF, health response, API errors and the Replit config. It does not contact or certify a real backend.

## 3. Publish the frontend demo

In Publishing, use **Autoscale** with these values (also recorded in `.replit`):

| Setting | Value |
| --- | --- |
| Build | `npm ci --include=dev && npm run build` |
| Run | `node scripts/serve.mjs` |
| Internal port | `5174` |
| External port | `80` |
| `PORT` | `5174` |

Keep the configured internal port and `PORT` aligned. The server accepts a different valid runtime port, but when explicit `.replit` port mappings are used, the mapping must match the actual listener. Do not expose extra test-backend/debugger ports in the deployment.

Default configuration is mock mode. There are ten fictional residents and a landlord; state is kept in browser memory and resets on reload. Files are not uploaded/parsed, and legal guidance remains withheld while review is unavailable. The mock server needs no model keys, database or external font/image service.

The production process must serve quickly; it reads the completed build and does not run ingestion, fetch laws, generate documents or start workers at startup.

## 4. Set environment values deliberately

| Variable | When it is used | Default / meaning |
| --- | --- | --- |
| `PORT` | Server runtime | `5174`; integer 1-65535 |
| `VITE_LAGA_MODE` | Frontend build / Vite dev | `mock`; set `api` only after backend acceptance |
| `VITE_LAGA_API_BASE` | Frontend build / Vite dev | `/api/v1`; full HTTPS API URL for direct remote access |
| `LAGA_API_PROXY` | Vite development server only | Upstream origin, default `http://127.0.0.1:8001` |
| `LAGA_CSP` | Production response header, optional | Custom CSP only if deliberately configured/tested |

Review the **production** environment/secrets in Publishing; do not assume development workspace values are present. `VITE_*` values become public browser JavaScript even if entered in a Secrets UI. Keep service credentials in the backend environment only. Changing a `VITE_*` setting requires rebuilding and republishing; changing only runtime values after a build will not rewrite the frontend.

The default server adds `nosniff`, a referrer policy, non-cacheable HTML and immutable caching for build assets. If setting a custom CSP, test both the app and API Explorer: the explorer compiles JSON schemas at runtime, so a policy that prohibits all dynamic compilation needs precompiled validators rather than an untested header copied from another app.

## 5. Connect a real backend later

The included production server **does not implement or proxy `/api`**. The development proxy is not included in the production build.

**Direct remote API:** set these in the publishing build environment, rebuild and publish:

```dotenv
VITE_LAGA_MODE=api
VITE_LAGA_API_BASE=https://your-api.example.com/api/v1
```

The backend must allow the actual published frontend origin (and any test/Preview origins you intend to support), credentialed CORS, the CSRF header and compatible cookies. HTTPS is required for production; verify browser cookie behavior, not just curl responses. Configure the explorer's server separately when testing it.

**Same-origin `/api/v1`:** keep `VITE_LAGA_API_BASE=/api/v1`, but route `/api` to a real service before requests reach this static server, or have the backend serve the built UI itself. A backend on another physical server can still be reverse-proxied through the application origin. Do not merely set `LAGA_API_PROXY` in Publishing and expect the Node production server to forward API traffic.

See `docs/BACKEND_CONNECTION.md` and the PDF handbook for topology examples, CORS/cookie/CSRF requirements and acceptance checks. The API Explorer is at `/api-docs/`; the Developer Tools entry appears on login/home screens as requested. Its presence is not an authorization mechanism.

For real data, the backend must provide authentication, ownership checks, private document storage, ingestion, review and audit. Use durable database/object storage for tenant files and shared state. Published app-local files are not durable application storage; the reference SQLite law cache needs an appropriate persistent/shared replacement or deployment strategy before production backend use.

## 6. Post-publish checks

On the published origin, verify:

1. `/` loads the UI and mock profiles work (or real login works if intentionally configured).
2. `/api-docs/` and `/api-docs` load the explorer; they are not captured by API routing.
3. Developer Tools on login/home reveals a stable API Docs link, and other pages stay free of that control.
4. The PDF handbook downloads from the explorer's connection guide; JS, CSS and fonts return 200.
5. `/healthz` returns HTTP 200 with `service: "laga-frontend"`.
6. In the standalone frontend configuration, `/api/v1/auth/session` and API mutations return JSON 503 `BACKEND_NOT_CONNECTED`, rather than HTML or demo API data. This is expected until routing/backend integration is supplied.
7. Ask Laga's composer is visible at supported desktop/mobile sizes and the policy library has no horizontal overflow.

For API mode, additionally run both roles against the actual published backend, including session refresh/logout, tenant isolation, upload concurrency, NC state inheritance and legal-review failure cases.

## Recovery checks

| Symptom | Action |
| --- | --- |
| Vite missing during build | Use the exact `npm ci --include=dev` command; do not build after an omit-dev install |
| Missing PDF or outside-root import | Import the full source bundle/root, including docs and contracts |
| Build missing or incomplete at startup | Confirm the build ran and includes `dist/index.html` plus `dist/api-docs/index.html` |
| Preview works, deployment fails | Review publishing build/run settings, production environment and port mapping |
| Failed port promotion | Listener must bind `0.0.0.0`; explicit `localPort` must match `PORT`, external port 80 |
| `/api` is 503 or login cannot work | Supply real backend routing or a full remote API base; static server is frontend-only |
| Cross-origin login loses its session | Check CORS origin, credentials, cookies, SameSite/Secure and CSRF/origin checks |
| Old frontend mode persists | Rebuild/republish after changing `VITE_*`; those settings are baked into assets |

## Platform references

Checked against Replit documentation on October 31, 2026:

- [Project configuration](https://docs.replit.com/features/project-setup/configuration)
- [Deployment types](https://docs.replit.com/features/publishing/deployment-types)
- [Publishing troubleshooting: ports, production settings and persistence](https://docs.replit.com/build/troubleshooting)

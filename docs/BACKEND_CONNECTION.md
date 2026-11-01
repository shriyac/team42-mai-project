# Test backend APIs and connect them to Laga

On the login page or a signed-in home dashboard, enable **Developer Tools** and choose **API Docs**. The link appears in a reserved row beneath the toggle; it is not a floating overlay. Developer Tools is intentionally absent from other workspace pages and resets on reload.

The API Explorer is available at **`/api-docs/`** in development and in the production build. Start the UI with `npm run dev` and open `http://localhost:5174/api-docs/`. On Windows PowerShell, use `npm.cmd` if script execution policy blocks `npm`.

This explorer uses `contracts/openapi.json` directly. It runs real browser requests, supports JSON and multipart PDF uploads, includes session cookies, captures CSRF tokens, and checks response schemas. It contains no mock backend and does not automatically connect the application after testing.

## 1. Test the backend independently

1. Set **Backend API base URL** to `/api/v1` for a same-origin route or development proxy, or to a full address such as `https://api.example.com/api/v1`. Select **Apply server**. Include the version prefix exactly once; endpoint paths are appended to it.
2. Send `GET /auth/session`. An anonymous session returns HTTP 200 with `data.user: null` and `data.csrfToken: null`.
3. Select `POST /auth/login`, replace the fictional credentials with a test account, and send. The backend sets its session cookie. A successful schema-valid response supplies the CSRF token, which the explorer captures automatically. The browser handles HttpOnly cookies; JavaScript cannot read them.
4. Test `GET /workspace` and a lease visible to that user. Copy real IDs from your responses into path parameters and JSON bodies. The example IDs are placeholders, not seeded backend records.
5. With a landlord account, register an NC property, upload a PDF, and test a new policy version using the current family ID and `expectedVersion`. Multipart requests let the browser set the boundary. Uploaded PDFs must be nonempty and at most 10 MiB; server-side type/content validation remains required.
6. Test clarification requests with a tenant account, landlord replies, and assistant responses with state-law review metadata. Use a test session for each role and log out between accounts.
7. Inspect HTTP status, response body, visible headers and schema errors. An error envelope may match the schema while the operation still fails. Export the test report for the integration handoff; it excludes bodies, passwords and CSRF tokens. The base URL, method, path template, HTTP status and schema check are included.

No requests execute merely by opening the explorer. Mutation endpoints act on the selected backend when **Send request** is chosen. Requests can be canceled and time out after 30 seconds. Canceling the browser request does not undo work already committed by the backend; check the workspace before retrying a mutation.

CSRF tokens, credentials and response data are held in page memory, not local/session storage. Reloading clears them. Changing the applied server clears captured authentication metadata, results and checks; it does not log out the old server or delete its cookies. Network errors may come from CORS, mixed content, certificates or an unavailable server; browsers do not expose detailed CORS failures to JavaScript.

The explorer is a developer tool. Publish it only to environments/audiences intended for testing, or restrict `/api-docs/` at your web server. It is not a replacement for backend authorization.

## 2. Choose a deployment topology

The physical server location and the browser's origin are separate choices. An origin is scheme + hostname + port; two services on the same machine but different ports are cross-origin.

| Arrangement | Browser calls | Application setting | Requirements |
| --- | --- | --- | --- |
| UI and API served under the same origin | `https://app.example.com/api/v1/...` | `/api/v1` | Route `/api` to the backend; no browser CORS needed |
| Backend on another server, reverse-proxied through UI origin | `https://app.example.com/api/v1/...` | `/api/v1` | Reverse proxy reaches the remote backend; preserve path and cookie behavior |
| Browser calls a separate API origin directly | `https://api.example.com/api/v1/...` | Full API URL | Credentialed CORS, HTTPS, compatible cookies and CSRF origin validation |

The reverse-proxy arrangement works whether the backend is local, in another container, or on a different server. It also avoids dependence on cross-site browser cookies. Use direct cross-origin hosting when your authentication and network configuration support it.

## 3. Connect in local development

Copy `frontend/.env.example` to `frontend/.env.local`:

```dotenv
VITE_LAGA_MODE=api
VITE_LAGA_API_BASE=/api/v1
```

Vite proxies `/api` to `http://127.0.0.1:8001` by default, preserving `/api/v1/...`. Your backend must serve that prefix.

To proxy to another development server, set `LAGA_API_PROXY` in the shell that starts Vite:

```powershell
$env:LAGA_API_PROXY='https://staging-api.example.com'
npm.cmd run dev
```

```sh
LAGA_API_PROXY=https://staging-api.example.com npm run dev
```

Use only the upstream origin for `LAGA_API_PROXY`, not `/api/v1`; Vite forwards the full incoming path. Use valid TLS certificates. The development proxy translates cookie domain/path attributes to the UI origin and `/` for local testing; do not configure Domain on host-only production cookies merely for Vite.

Alternatively bypass the proxy and set:

```dotenv
VITE_LAGA_MODE=api
VITE_LAGA_API_BASE=https://staging-api.example.com/api/v1
```

That second configuration requires the backend to allow the actual frontend origin, typically `http://localhost:5174`. HTTPS API cookies and browser third-party cookie restrictions may prevent cross-site session testing from localhost; use the development proxy or a same-site HTTPS test environment if needed. Restart Vite after changes to `.env` or shell configuration. The explorer can test an API while the application remains in mock mode.

## 4. Connect in production

Set `VITE_LAGA_MODE=api` and `VITE_LAGA_API_BASE` in the environment used for **`npm run build`**. Deploy the generated `dist/` directory. Vite embeds these settings during the build; changing server environment variables after serving a build does not change that build's API target. Rebuild/redeploy to change it. Never put secrets in `VITE_*` variables.

For a same-origin setup, a reverse proxy can serve the built UI and route `/api/` to a backend. This Nginx example preserves the `/api/v1/...` path:

```nginx
server {
    listen 443 ssl;
    server_name app.example.com;
    # Configure your certificate/key and standard TLS settings here.
    root /srv/laga/dist;

    location /api/ {
        # No trailing URI slash: preserve the original /api/v1/... path.
        proxy_pass http://backend.internal:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        client_max_body_size 12m;
    }

    location /api-docs/ {
        try_files $uri $uri/ =404;
        # Apply your organization's developer-only access rules here if hosted.
    }

    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

The backend must trust forwarded headers only from known proxies. Configure host/origin checks and host-only cookie attributes for the browser-visible application origin. If proxying an HTTPS upstream, configure upstream certificate verification, SNI and the expected upstream Host explicitly with your hosting team. The example uses an internal HTTP upstream, not a complete production infrastructure configuration.

The included `npm start` static server serves `/api-docs/` and the built UI, but **does not proxy or implement `/api`**. Front it with a reverse proxy for same-origin API mode, or use a full cross-origin API URL at build time.

## 5. Direct cross-origin configuration

For a frontend at `https://app.example.com` calling `https://api.example.com`, return these headers on allowed actual responses, including error responses:

```http
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Vary: Origin
```

For allowed preflight requests, respond without requiring an authenticated session:

```http
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Access-Control-Allow-Methods: GET, POST, DELETE, OPTIONS
Access-Control-Allow-Headers: Content-Type, X-CSRF-Token
Vary: Origin
```

Use an explicit allowlist of frontend/tester origins, including scheme and port. Do not reflect arbitrary origins or use `Access-Control-Allow-Origin: *` with credentials. If using an HTTP request-ID header, expose it explicitly with `Access-Control-Expose-Headers`; the JSON error `requestId` remains available without this. Cookies belong to the API host in this topology. Keep them HttpOnly and Secure in production; choose a Path that covers the API.

Cross-origin is not always cross-site: HTTPS subdomains of the same registrable domain are normally same-site. Truly cross-site session cookies generally require `SameSite=None; Secure`, and browser third-party cookie restrictions can still block them even with valid CORS. Do not disable CSRF protection to make CORS work. Allow the intended frontend origin in login/CSRF checks and keep `X-CSRF-Token` validation on authenticated mutations.

An HTTPS frontend must not call an HTTP API. Any configured Content Security Policy must allow the direct backend origin in `connect-src`. Use a same-origin proxy when direct browser sessions cannot be made reliable in supported browsers.

## 6. Integration acceptance

- Implement every endpoint and DTO in `contracts/openapi.json`, including response envelopes. Follow `docs/INTERFACE_CONTRACT.md` for behavior beyond schemas.
- Run `npm test`, `npm run build`, and your backend's endpoint tests. Existing mock/adapter tests do not prove that your deployed service behaves correctly.
- Export explorer results per backend/environment. Passing schema checks are structural evidence, not proof of tenant isolation, legal accuracy, ingestion correctness or operational readiness.
- Exercise the actual app in API mode with both roles: login/session/logout, property registration, tenant projection, queries, requests/replies, NC tagging, concurrent policy versions and date boundaries.
- Require fresh, scope/date/content-bound compliance reviews before policy retrieval and final assistant answers. Government-source caching is shared, but each new document/final answer needs its own assessment.
- Confirm failure behavior for missing/stale review, ingestion failure, API outage, 401, 403, 409 and invalid uploads. No API failure should silently select mock data.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| `/api` returns 503 `BACKEND_NOT_CONNECTED` | Static server is receiving the request; add a reverse proxy or use a full API URL |
| 404 on all API endpoints | Full base prefix should be `/api/v1`; proxy must preserve it exactly once |
| HTML or login page instead of JSON | SPA fallback or authentication gateway intercepted `/api`; fix routing |
| “Cannot reach this API” | Server/TLS, browser console, HTTPS mixed content, CORS or CSP |
| Login succeeds but workspace is 401 | Cookie host/path, credentials, SameSite/Secure, browser cookie policy |
| Mutations are 403 | Capture session CSRF token; verify origin allowlist and token header validation |
| “Response does not match contract” | Compare response envelope and DTO with the model inspector/OpenAPI |
| Answer withheld after a passed review | Review expiry, exact final-text hash, NC state, scope, reference date and official citations |
| App still displays demo mode | Set `VITE_LAGA_MODE=api`, restart Vite or rebuild/redeploy |

## References

- [Vite environment variables](https://vite.dev/guide/env-and-mode): client configuration is replaced during the build.
- [MDN CORS guide](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS): credentialed requests, preflight and cookie restrictions.

- [Nginx proxy_pass](https://nginx.org/en/docs/http/ngx_http_proxy_module.html#proxy_pass): upstream URI forwarding behavior.
- [Vite server proxy](https://vite.dev/config/server-options.html#server-proxy): development proxy configuration.

State-law verification is disabled by default for both landlord and tenant experiences. Set `VITE_LAGA_STATE_VERIFICATION=true` in the build environment to enable review cards, policy review status and review-based answer/policy gating. Restart development or rebuild/redeploy production after changing it. When off, document processing, effective dates, state tagging and authorization remain enforced; answers carry no claim of legal verification. This public frontend flag does not disable a backend?s independent legal checks or start/stop its law-fetching jobs. Configure those separately in the backend; no flag is sent as a client-controlled permission bypass. The API contract and review metadata remain unchanged.

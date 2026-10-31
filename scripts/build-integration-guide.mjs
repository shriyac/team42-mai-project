import fs from 'node:fs/promises';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
const root=fileURLToPath(new URL('../',import.meta.url));
const read=name=>fs.readFile(path.join(root,name),'utf8');
const specText=await read('contracts/openapi.json'),spec=JSON.parse(specText);
const examples=JSON.parse(await read('contracts/integration-examples.json'));
const fullExamples=JSON.parse(await read('contracts/examples.json'));
const connection=await read('docs/BACKEND_CONNECTION.md'),contract=await read('docs/INTERFACE_CONTRACT.md');
const hash=createHash('sha256').update(specText).digest('hex');
const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function inline(text){return esc(text).replace(/`([^`]+)`/g,'<code>$1</code>').replace(/\*\*([^*]+)\*\*/g,'<strong>$1</strong>').replace(/\[([^\]]+)\]\((https?:[^)]+)\)/g,'<a href="$2">$1</a>')}
const code=(value,caption='')=>(caption?`<p class="code-caption">${esc(caption)}</p>`:'')+`<pre>${esc(typeof value==='string'?value:JSON.stringify(value,null,2))}</pre>`;
function table(headers,rows){return `<table><thead><tr>${headers.map(h=>`<th>${inline(h)}</th>`).join('')}</tr></thead><tbody>${rows.map(row=>`<tr>${row.map(cell=>`<td>${inline(cell)}</td>`).join('')}</tr>`).join('')}</tbody></table>`}
function markdown(text){
 const raw=[];
 text=text.replace(/(<table>[\s\S]*?<\/table>|<pre>[\s\S]*?<\/pre>|<p class="[^"]*">[\s\S]*?<\/p>)/g,block=>{raw.push(block);return '\n\n@@HTMLBLOCK'+(raw.length-1)+'@@\n\n'});
 const lines=text.trim().split(/\r?\n/);let out='',i=0;
 while(i<lines.length){const line=lines[i];if(!line.trim()){i++;continue}
  if(/^@@HTMLBLOCK\d+@@$/.test(line)){out+=raw[Number(line.match(/\d+/)[0])];i++;continue}
  if(line.startsWith('```')){const language=line.slice(3);let body=[];i++;while(i<lines.length&&!lines[i].startsWith('```'))body.push(lines[i++]);i++;out+=code(body.join('\n'),language);continue}
  if(/^#{1,6} /.test(line)){out+=`<h3>${inline(line.replace(/^#+ /,''))}</h3>`;i++;continue}
  if(line.startsWith('|')&&lines[i+1]?.match(/^\|[\s:|-]+\|$/)){const cells=s=>s.trim().slice(1,-1).split('|').map(x=>x.trim());const headers=cells(line),rows=[];i+=2;while(lines[i]?.startsWith('|'))rows.push(cells(lines[i++]));out+=table(headers,rows);continue}
  if(/^(?:- |\d+\. )/.test(line)){const ordered=/^\d/.test(line);let items=[];while(i<lines.length&&/^(?:- |\d+\. )/.test(lines[i]))items.push(`<li>${inline(lines[i++].replace(/^(?:- |\d+\. )/,''))}</li>`);out+=`<${ordered?'ol':'ul'}>${items.join('')}</${ordered?'ol':'ul'}>`;continue}
  const paragraph=[];while(i<lines.length&&lines[i].trim()&&!/^(?:```|#{1,6} |\||- |\d+\. )/.test(lines[i]))paragraph.push(lines[i++]);if(!paragraph.length){paragraph.push(lines[i++])}out+=`<p>${inline(paragraph.join(' '))}</p>`;
 }return out;
}
function extract(document,heading){const start=document.indexOf(heading);if(start<0)throw Error('Missing source section: '+heading);const content=document.slice(start+heading.length);const end=content.search(/\n## /);return (end<0?content:content.slice(0,end)).trim()}
const sections=[];
function add(title,body,{group='Implementation',html=false}={}){sections.push({id:'section-'+(sections.length+1),title,group,html:html?body:markdown(body)})}

add('01 / Start here: the integration route',`
This handbook is for backend engineers, integration testers and the person deploying Laga. It describes the contract the existing frontend consumes. Backend language and framework are your choice; keep the HTTP behavior and DTOs consistent.

### Read this first
1. Use contracts/openapi.json, version ${spec.info.version}, as the machine-readable API definition. This PDF explains behavior and includes its complete field reference.
2. Build the 11 routes under /api/v1. Use the response envelopes exactly; do not return raw database objects.
3. Test independently in the API Explorer. Then test the application in API mode with both roles. Those are separate acceptance steps.
4. Choose a deployment topology. The backend's physical server does not need to be the frontend's server.
5. Connect by configuration, restart or rebuild, and run the acceptance matrix in this handbook. A conforming backend should not require React component changes.

### One-minute navigation
- Application: http://localhost:5174 after starting the local development server.
- Explorer: turn on Developer Tools on the login page or home dashboard, then choose API Docs. The toggle is not shown on lease, conversation or document pages.
- Direct explorer address: http://localhost:5174/api-docs/.
- Standalone kit: extract laga-api-testing-kit-v${spec.info.version}.zip and run node scripts/serve.mjs from its root; no npm installation is required for the built kit.
- Full repository: Node.js 22+, npm ci, then npm run dev. On PowerShell, use npm.cmd if npm.ps1 is blocked.

### What a successful handoff includes
A backend URL, implemented contract version, provisioned test accounts, representative IDs, documented hosting/auth settings, exported explorer results, backend test evidence and end-to-end application sign-off. A green response-schema check alone is insufficient.

### Status of the software
The UI and explorer exist. The current default is a fictional mock workspace. The reusable Python law-cache/reviewer boundary exists, but authentication, durable data, real PDF ingestion, retrieval/model execution and a qualified legal reviewer still need production backend implementation. This PDF does not certify any uploaded lease or policy as lawful.
`);

add('02 / Files, ownership and environments',`
### Source-of-truth order
Use the OpenAPI document for transport shapes and paths, the behavioral contract for authorization/timelines/review invariants, and the frontend adapter for the exact browser call behavior. If they disagree, resolve the discrepancy before implementation; do not silently introduce a second API shape.

${table(['File or artifact','Purpose'],[
 ['contracts/openapi.json','OpenAPI 3.1; all routes, JSON schemas, authentication declarations and documented responses.'],
 ['contracts/examples.json','Complete fictional session/workspace/lease/answer envelopes for comparison.'],
 ['contracts/integration-examples.json','Request fixtures and a synthetic passed-review answer; timestamps expire.'],
 ['frontend/src/services/httpGateway.js','Application HTTP adapter: credentials, CSRF, envelope handling and answer-review display guard.'],
 ['frontend/src/lib/compliance.js and policies.js','Exact review identity/freshness checks used by the frontend.'],
 ['frontend/src/api-docs/','Independent request tester generated from the shared spec; not a live backend.'],
 ['src/laga/compliance.py','Reusable SQLite source cache and default-deny reviewer boundary; not an API service.'],
 ['docs/BACKEND_CONNECTION.md','Editable connection/deployment instructions.'],
 ['docs/INTERFACE_CONTRACT.md','Behavioral implementation agreement.']])}

### Division of work
The backend owns sessions, role/organization authorization, data persistence, private files, ingestion, effective-date filtering, review implementation, model calls, deterministic calculations and audit records. The frontend owns rendering and browser request mapping. The deployment owner owns HTTPS, routing, cookie/origin configuration, CORS where necessary and the correct environment at build time.

### Environments are explicit
Use separate development/staging/production accounts, storage and secrets. Example IDs and fictional credentials are not real seeded records. Record the backend base URL and contract version in every test report. The explorer's target and the application's API configuration are independent.
`,{html:false});

add('03 / Decide how the API is reached',extract(connection,'## 2. Choose a deployment topology')+`

### The integration boundary
Browser -> /api/v1 route -> your HTTP service -> authorized data/files -> ingestion/review/retrieval workers. Worker-to-worker protocols and database schemas are internal implementation choices; the UI consumes the HTTP DTOs described here.

### Recommended default while hosting is undecided
Keep the browser-facing API base as /api/v1 and use a reverse proxy. This works with a backend on the same machine, another container, or another server. If the browser must call the API origin directly, use the full HTTPS API base and configure the cross-origin requirements in chapter 08.

### Prefix examples
- Correct explorer/application base: https://api.example.com/api/v1.
- Correct development proxy origin: https://staging-api.example.com.
- Incorrect proxy target: https://staging-api.example.com/api/v1 when the incoming path already contains /api/v1. This can duplicate the prefix.
- The /api-docs/ page is frontend content; it must not be forwarded by a broad /api prefix rule.
`);

add('04 / HTTP, sessions and error envelopes',extract(contract,'## Transport and authentication')+`

### Compatibility details that often break integrations
- Creation endpoints return HTTP 200, not 201, under this contract. Logout and cancellation return JSON envelopes, not 204.
- Use Content-Type: application/json on JSON responses, including errors. The explorer validates the media type and the documented status-specific envelope.
- The OpenAPI security scheme names the cookie laga_session. Keep its content opaque and server-managed.
- Origin validation on login is compatible with the current frontend. An extra pre-authentication token exchange or header not in this contract requires a coordinated change.
- The application sends {} on logout; the explorer sends no body because no request body is specified. Accept both without requiring extra fields.
- A 401 is a sign-in failure/session-expiry path. A 403 is an authenticated denial, and should not erase a valid session. A foreign tenant object should ordinarily be hidden with 404.
- The API must authorize data before returning it. Hiding a menu or toggling Developer Tools is not authorization.
`);

add('05 / Dates, identities and DTO conventions',`
### Stable identities and units
IDs are opaque strings. Persist relationships explicitly: tenant -> authorized lease -> property -> state. Bind all landlord records to the authenticated organization internally; an organization ID need not be accepted from the browser. A URL ID or thread ID never grants access.

Money is integer USD cents throughout DTOs and calculation inputs/results. For example, 220000 means USD 2,200.00. Do not return a formatted currency string where an integer is required. Unknown values must not become zero silently.

### Dates have two distinct meanings
Calendar dates use YYYY-MM-DD, such as effectiveFrom and asOf. Validate real dates, not only the regex: 2026-02-30 is invalid. Instants such as uploadedAt, createdAt, checkedAt and expiresAt carry offsets; UTC Z is a good interoperable choice.

Workspace.timeZone is an IANA zone. For an NC property, configure America/New_York as appropriate to the real property/business rules. Persist the policy family's time zone so old intervals do not change when display settings change. The demo currently exposes America/Chicago and a frozen asOf of 2026-10-30; those are fixture values, not deployment defaults or today's business date.

Policy intervals are half-open: effectiveFrom <= asOf and (effectiveTo is null or asOf < effectiveTo). A predecessor ending 2026-11-15 is excluded on November 15. Its replacement starts that day.

### Required, optional and nullable are different
If a required field is unknown and its type allows null, include it with null. Do not omit it. Optional fields may be omitted, but cannot be null unless the type permits it. Most object schemas set additionalProperties: false; do not append debug, database or model fields to them.

### Small-portfolio contract
Workspace returns the current authorized collection without pagination. Its summary must be calculated from the same authorized lease/property set. Avoid double-counting shared tenants as occupied units. Empty arrays are valid, but the backend must define intentional behavior for a tenant without a provisioned lease; the home page shows a getting-ready empty state when no lease is assigned; provision the association before testing lease-dependent flows.

Property.style is a required UI illustration key: willow, juniper or cedar. Supply a supported default even if your database has no illustration concept. User.role is tenant or landlord; Customer is a UI label for tenant. Permissions are exact strings, not display labels.
`);

add('06 / Test in the API Explorer',`
### Entry from the user interface
On the login page or a signed-in home dashboard, enable Developer Tools. API Docs appears in its reserved row and opens the explorer in another tab. This does not change your role, backend permissions or the application's mock/API mode. The toggle does not appear on other workspace pages. It resets when the page reloads.

${extract(connection,'## 1. Test the backend independently')}

### What a green result means
It means the actual HTTP status is documented, the body is JSON with the expected media type, and its shape matches that response schema. It does not establish authorization, correct arithmetic, legal validity or the completeness of a government source. An HTTP 401 can have a correctly shaped error envelope; that is not a successful endpoint test.

### Tester versus application
The explorer performs full schema checks using AJV with format checks disabled. Calendar dates and timestamp semantics still require server validation. The application adapter performs envelope/error handling and additional answer-review checks, but is not a full DTO validator. Do not rely on the browser to enforce backend correctness.

The explorer rejects redirects. Use final API routes that return JSON directly; do not redirect API callers to HTML sign-in pages. The application adapter has no explicit timeout, while explorer calls time out after 30 seconds. Do not use the explorer's timeout as a backend job-completion guarantee.
`);

add('07 / Connect in development',extract(connection,'## 3. Connect in local development')+`

### Reproducible repository startup
From the repository root, run npm ci followed by npm run dev. Python 3.11+ is required for the reference compliance module and its tests, not for serving the built static testing kit. Your backend framework may have its own requirements.

### Change only configuration for a conforming API
Set VITE_LAGA_MODE=api. Keep VITE_LAGA_API_BASE=/api/v1 when using the development proxy; use a full API URL only for direct browser access. No VITE_* variable may contain a service secret. LAGA_API_PROXY is a development-server setting, not a deployed browser setting. Restart the Vite process after changing it.
`);
add('08 / Deploy behind a same-origin route',extract(connection,'## 4. Connect in production')+`

### Verify routing before testing business logic
GET /api/v1/auth/session must reach the API and return its JSON Session envelope. GET /api-docs/ must reach frontend assets. The SPA fallback must not convert an API 404 into index.html. Preserve the API prefix; preserve usable cookie attributes and configure forwarded-header trust deliberately.

### Internal service authentication
If a deployment gateway or private upstream requires a service credential, keep it in the proxy/service environment. Do not place it in frontend assets or add it to a public VITE_* variable. Gateway-specific requirements must be documented by the hosting owner.
`);
add('09 / Deploy with direct cross-origin calls',extract(connection,'## 5. Direct cross-origin configuration')+`

### Confirmation sequence
1. Open browser developer tools and inspect the OPTIONS preflight for login/mutation requests.
2. Confirm the allowed Origin is exact and Access-Control-Allow-Credentials is true.
3. Confirm the login response sets the expected cookie and a subsequent GET /workspace sends it.
4. Confirm authenticated POST/DELETE requests send X-CSRF-Token and the server validates it.
5. Verify both an allowed frontend origin and a disallowed origin. Also check error responses carry the allowed CORS headers so the browser can display their safe messages.

Do not test only with curl. Curl does not enforce browser CORS, SameSite or third-party cookie restrictions. Browser end-to-end evidence is required for the selected topology.
`);

add('10 / Endpoint map and implementation order',`
${table(['Phase','Routes','Exit criterion'],[
 ['1. Identity','POST /auth/login; GET /auth/session; POST /auth/logout','Both roles authenticate; cookie/CSRF lifecycle and anonymous session work.'],
 ['2. Authorized read model','GET /workspace; GET /leases/{id}','Tenant and organization isolation; correct IDs, dates, cents and summary.'],
 ['3. Property / requests','POST /properties; POST /requests; POST /requests/{id}/reply','NC registration and cross-role clarification workflow work.'],
 ['4. Policy lifecycle','POST /policies; DELETE /policies/{id}','Async ingestion, immutable versions, concurrency and cancellation behave correctly.'],
 ['5. Assistant / review','POST /assistant/messages','Scoped retrieval and final answer checks fail closed; review metadata is fresh and bound.']])}

### Shared success rules
All 11 operations return HTTP 200 with a data envelope on success. Protected routes require a session; authenticated mutations require X-CSRF-Token. Every operation's complete schema is in the OpenAPI file and the dictionary at the end of this handbook.

### Public versus protected
Only login and session are declared available before authentication. The public session route must safely return an anonymous Session. Property registration and policy writes require the landlord's policies:write permission under the current contract; do not invent a differently named permission without coordinating UI/schema changes.

### Implemented browser interface
The API Explorer can test any documented route, including operations a tenant cannot use. The backend must enforce role and object checks regardless of the request source. The ordinary app exposes operations according to its workspace role and permissions.
`);

const notes={
 '/auth/login':{who:'Public credential exchange; server selects role and permissions.',request:examples.login,steps:['Validate credentials with generic failure messages, rate limiting and a trusted-origin login policy.','Rotate/create the session; set the session cookie and return User plus csrfToken.','Never accept role, tenantId or permissions from this login body. Those fields exist only in mock login.'],verify:'Use real test accounts for both roles. Check HTTP 200, Set-Cookie in browser tools, and a schema-valid Session. Wrong credentials must not leak account existence.',errors:'401 invalid credentials; 422 invalid fields; 429 rate limit. Response details must remain user-safe.'},
 '/auth/session':{who:'Public session lookup; no CSRF header required for GET.',request:null,steps:['Read and validate the server session cookie if present.','Return the authenticated User and CSRF token when valid.','Return user:null and csrfToken:null for an anonymous visitor; do not treat ordinary anonymity as 401.'],verify:'Test before login, after login, after reload and after logout. The app restores its workspace from this route.',errors:'A missing cookie is a successful anonymous Session. Use 503 for genuine service unavailability, not a fabricated authenticated user.'},
 '/auth/logout':{who:'Authenticated user; X-CSRF-Token required.',request:null,steps:['Validate the session and CSRF token.','Invalidate the server session and expire its browser cookie.','Return data:{signedOut:true}. The current application sends an empty JSON object; the explorer can send no body.'],verify:'After a successful logout, GET /auth/session must be anonymous and the old session must not authorize protected reads.',errors:'401 expired session; 403 bad CSRF. Do not return 204, HTML or a bare boolean.'},
 '/workspace':{who:'Authenticated user; tenant projection or landlord organization projection.',request:null,steps:['Resolve the session to its tenant/organization scope before any data query.','Return user, asOf, timeZone, properties, leases, tenants, requests, policies and summary. Include state on property/policy records.','Compute summary from the returned authorized active set; expose ingestion and compliance as separate statuses.'],verify:'Compare two tenants and two organizations. A tenant must never receive another tenant\'s records, including in summary or sources.',errors:'401 anonymous; 503 unavailable read model. Do not return empty mock data when an API call fails.'},
 '/properties':{who:'Authenticated landlord with policies:write; organization-scoped creation.',request:examples.propertyRegistration,steps:['Validate trimmed nonempty name/address/city; NC state; integer units from 1 through 10000.','Create the property under the authenticated organization, not a browser-supplied owner.','Return a complete Property including opaque id, state, style and amenities. Empty amenities is valid.'],verify:'NC registration succeeds. Missing/foreign state, invalid units, tenant writes and cross-organization assignment fail.',errors:'403 wrong role/permission; 422 invalid values. HTTP 200 is the declared creation success status.'},
 '/leases/{id}':{who:'Authenticated landlord in owning organization, or the tenant authorized for this lease.',request:null,steps:['Resolve the encoded path id as an opaque value.','Check organization/tenant ownership before returning the lease or any clauses.','Return LeaseDetail: lease, clauses, property and tenant. Source quotes must retain their real document references.'],verify:'Use a real lease ID obtained from the current workspace. A foreign tenant lease must return 404 without identifying its owner.',errors:'404 invisible/missing lease; 401 anonymous. Never infer authorization from an ID prefix.'},
 '/assistant/messages':{who:'Authenticated user; portfolio only for authorized landlords; lease scope must be owned/visible.',request:examples.ask,steps:['Validate the question, scope and real calendar asOf. Bind thread ownership/scope/date server-side.','Derive jurisdiction from authorized properties. Resolve policy versions and readiness before every retrieval branch.','Generate only supported content, validate the final answer and calculations, then return Answer with review metadata.','If evidence/review/coverage is incomplete, return a safe needs_clarification response with no unreviewed legal claims.'],verify:'Test lease and portfolio scopes; foreign leases; changing reference dates; pending replacements; expired reviews; altered final text; missing official citations.',errors:'403 unauthorized portfolio; 404 invisible lease/thread; 422 invalid input. Safe clarification is a successful 200 Answer, not a guessed answer.'},
 '/requests':{who:'Authenticated tenant; leaseId must belong to that tenant.',request:examples.clarificationRequest,steps:['Validate subject/message lengths and the chosen visible lease.','Assign tenantId from the session; create an open request with a server timestamp.','Return the complete Request, including reply:null.'],verify:'The request appears only for its tenant and owning landlord organization. Another tenant cannot read or reply to it.',errors:'403 landlord creating a tenant-only request; 404 invisible lease; 422 invalid content. Request category is a string, not the policy-category enum.'},
 '/requests/{id}/reply':{who:'Authenticated landlord authorized for the request\'s organization.',request:examples.landlordReply,steps:['Resolve the request under the current organization and validate reply text.','Record the reply, mark status answered and retain audit identity/time internally.','Return the complete updated Request, not a reply-only object.'],verify:'The owning tenant sees the reply after workspace refresh. Foreign organizations and tenants cannot reply.',errors:'403 wrong role; 404 invisible request; 422 blank/invalid reply. No separate request-list endpoint is defined; workspace carries requests.'},
 '/policies':{who:'Authenticated landlord with policies:write; PDF multipart upload.',request:examples.newPolicyMultipart,steps:['Validate private PDF bytes, nonempty size <=10 MiB, type/magic, native text availability and safe storage handling.','Validate state NC against every scoped property. New families require title/category; versions require familyId/expectedVersion.','In one transaction, lock the family, enforce chronological effectiveFrom, append the version and close its predecessor interval.','Return PolicyVersion promptly, with ingestion uploaded/processing and compliance pending. Process/review asynchronously.'],verify:'Upload one PDF per request. Test new families, a new version, stale expectedVersion, invalid state/file, processing failure and effective-date blocking.',errors:'409 VERSION_CONFLICT for stale/concurrent/date conflicts; 413 too large; 422 invalid PDF/fields. Detailed lifecycle rules follow in chapter 11.'},
 '/policies/{id}':{who:'Authenticated landlord with policies:write; owning organization only.',request:null,steps:['Treat DELETE as cancellation of an eligible staged future version, not permanent history deletion.','Require latest version, future effectiveFrom, non-ready ingestion and no successor.','Atomically restore the predecessor\'s prior open boundary, remove it from active workspace output and retain a cancellation audit record.','Return data:{deleted:true}.'],verify:'Cancel a future pending version and verify its predecessor remains applicable. Reject attempts to delete an effective, ready or superseded revision.',errors:'409 VERSION_CONFLICT for immutable/ineligible history; 404 invisible/missing version. Use new versions for corrections.'}
};
const ops=Object.entries(spec.paths).flatMap(([url,item])=>Object.entries(item).map(([method,op])=>({url,method,...op})));
for(const [index,op] of ops.entries()){
 const note=notes[op.url],content=op.requestBody?.content,requestSchema=content?Object.values(content)[0].schema:null;
 let sample=note.request;
 if(op.url==='/policies')sample={...examples.newPolicyMultipart,file:'<binary native-text PDF part; not this placeholder string>'};
 const params=(op.parameters||[]).map(p=>[p.name,p.in,p.required?'Yes':'No',p.schema?.type||'string']);
 const response=op.responses['200'].content['application/json'].schema.properties.data.$ref.split('/').at(-1);
 let html=`<div class="endpoint-badge ${op.method}">${esc(op.method.toUpperCase())}</div><p class="endpoint-path">/api/v1${esc(op.url)}</p><p><strong>Purpose:</strong> ${esc(op.summary)}</p><p><strong>Access:</strong> ${esc(note.who)}</p>`;
 if(params.length)html+='<h3>Path and header parameters</h3>'+table(['Name','Location','Required','Type'],params);
 html+='<h3>Request</h3><p>'+(content?`Content type: <code>${esc(Object.keys(content)[0])}</code>. Model: <code>${esc(requestSchema.$ref.split('/').at(-1))}</code>.`:'No request body is required.')+'</p>';
 if(sample)html+=code(sample,op.url==='/policies'?'Multipart field map for illustration; choose a real file in the explorer':'JSON example; replace IDs/credentials with your test records');
 html+='<h3>Server implementation sequence</h3><ol>'+note.steps.map(step=>`<li>${esc(step)}</li>`).join('')+'</ol>';
 html+=`<p><strong>Success:</strong> HTTP 200 with <code>{ "data": &lt;${esc(response)}&gt; }</code>. See the complete <code>${esc(response)}</code> field reference and companion examples.</p><p><strong>Verification:</strong> ${esc(note.verify)}</p><p><strong>Failure behavior:</strong> ${esc(note.errors)}</p>`;
 add(`E${String(index+1).padStart(2,'0')} / ${op.method.toUpperCase()} ${op.url}`,html,{group:'Endpoint reference',html:true});
}

add('11 / Policy storage, versions and async processing',extract(contract,'## Policy families, versions and effective dates')+`

### Ingestion and legal review are independent
A ready document is fully extracted and indexed, not automatically law-compliant. The backend must require both ready ingestion and a current passed legal review before retrieval. Do not overload status with legal outcomes; use compliance.status for those.

### Job integration without extra UI endpoints
The HTTP response represents a durable accepted version, not a finished job. Workers update stored ingestion/compliance metadata. The current UI reloads it through GET /workspace when Refresh is chosen. No job-status, retry, progress stream or ingestion callback endpoint is defined for the frontend yet. Implement internal queues/callbacks privately and coordinate any browser-visible extension.

### Dates and concurrency: worked boundary
If v2 is effective from 2026-07-01 and v3 starts 2026-11-15, v2.effectiveTo becomes 2026-11-15. Querying November 14 selects v2; querying November 15 selects v3. If v3 is still processing or its review is unavailable, the answer must clarify. It must not use v2 as a substitute. A second writer using expectedVersion=2 after v3 exists must receive 409.

### Upload response and retries
Persist the accepted upload and version metadata transactionally with a recoverable job/outbox mechanism appropriate to your stack. No Idempotency-Key header is specified. If a client times out, reload workspace before retrying; do not assume timeout means nothing was saved. A staged upload may be accepted even if a worker or legal source is temporarily unavailable, but must remain visibly ineligible for guidance.
`);

add('12 / NC state and compliance behavior',`
### Jurisdiction is property data
Property registration captures state: NC. Every corpus/version upload is tagged to NC and must match all properties in its scope. New versions inherit the family's state, category and property scope. Separate states would require separate policy families and coordinated source/UI/schema support; only NC is configured now.

Tenants never choose a state. Resolve it from the authorized lease and property. Portfolio legal questions must be evaluated per authorized property; the current single-state wire guard expects NC. A policy with propertyId:null is organization-wide within its state; do not accidentally apply it to a later property in another state.

### Shared laws, separate assessments
Fetch government-source snapshots once per state and reuse them for uploads and answers. The reference cache refreshes after one day and stores source content, URLs, fetchedAt, expiresAt and a content-derived revision. Reusing the laws does not reuse a verdict for a different document or answer.

The configured sources are the NC General Assembly Chapter 42 HTML and the NC Department of Justice renting guidance. The reference fetcher rejects redirects and oversized/unexpected source responses. A missing source, refresh failure or unsupported state blocks review. Add source monitoring/recovery so a changed government URL is not mistaken for a valid empty corpus.

### Reviewer outcomes
- pending: document/source data may exist, but review has not established complete coverage.
- passed: trusted review of the exact content, scope and date completed with current source metadata, official citations and no unresolved findings.
- conflict: rules or claims require changes; preserve useful clause-level findings for review.
- unavailable: the required source/reviewer/check could not be completed or verified.

No model confidence score substitutes for coverage. Uploaded text is untrusted evidence, never reviewer instructions. Assess applicable exceptions, amendments and federal/local requirements too. A cached current chapter cannot establish historical/future law by itself. Do not approve an unsupported date merely because a current source was downloaded.

### Default-deny behavior
The Python module returns pending when no reviewer is connected. It is a reusable boundary, not a legal reasoning engine or HTTP server. The backend must supply qualified review logic and enforce the result before releasing guidance. The frontend's display checks are additional safeguards, not a security or legal certification boundary.
`);

add('13 / Exact review metadata and hashing',`
### Required metadata when status is passed
The review identifies state, kind, scopeKey, exact asOf, checkedAt, expiresAt, 64-character lowercase hexadecimal lawRevision/contentHash and at least one official citation with a nonempty section. Findings must be absent or empty on a passed result. The metadata object rejects undeclared top-level fields.

${table(['Review target','kind','Exact scopeKey'],[
 ['Lease answer','answer','lease:<authorized lease id>'],['Portfolio answer','answer','portfolio:all'],['Property-specific policy','policy','property:<authorized property id>'],['Organization-wide NC policy','policy','state:NC']])}

### Answer identity
Hash the exact final UTF-8 answer string, not its JSON serialization, citations, a normalized copy, or an earlier draft. Preserve whitespace and newlines consistently. The backend validates the final answer and all calculations before release; its internal audit record must bind calculation results too, even though this wire contentHash checks the answer string only.

${code('import hashlib\ncontent_hash = hashlib.sha256(\n    final_answer.encode("utf-8")\n).hexdigest()','Python: final answer hash')}

### Policy identity
Define and persist the canonical extracted text used for review; hash exactly those UTF-8 bytes. Return that value in both PolicyVersion.contentHash and compliance.contentHash. Preserve the original PDF checksum separately in storage/audit. Do not hash a short excerpt or mutate the canonical text after approval.

### What the current frontend actually checks
For supported API answers, it checks NC, exact asOf/kind/scopeKey, parseable timestamps with checkedAt <= now < expiresAt, hash formats, allowed citation URLs/sections, empty findings and the exact answer hash. The policy helper additionally compares its stored contentHash and property/state scope. It checks the shape of lawRevision; it cannot independently know the backend's latest law revision or your reviewer quality. The backend must enforce active law/source validity, organization ownership and revocation.

All supported API answers, including portfolio summaries, pass through the answer-review guard. The mock portfolio's example behavior is not an exemption in API mode. Any genuinely exempt factual-response category needs a coordinated contract/UI change.
`);

add('14 / Reviewer integration and safe clarification',`
### Reference Python call
The module uses only Python's standard library. Point LawCache at a writable persistent SQLite file; the caller supplies trusted scope and property states after authorization. Its BEGIN IMMEDIATE lock deduplicates a refresh across processes sharing that file. At production scale, choose the storage/locking strategy appropriate to your deployment rather than placing unrelated work behind a global file lock.

${code('from laga.compliance import LawCache, review\n\ncache = LawCache("/private-data/state-laws.sqlite")\nassessment = review(\n    cache,\n    state="NC",\n    property_states=["NC"],\n    text=final_answer,\n    as_of=request.as_of,\n    kind="answer",\n    scope_key="lease:" + authorized_lease.id,\n    reviewer=trusted_server_reviewer,\n)\n# Authorize + validate calculations separately.\n# Release supported guidance only if assessment passed.','Reference boundary; application/framework plumbing omitted')}

The reviewer receives text, laws, as_of, kind and scope_key as keyword arguments. A passing assessment must include status:passed, coverageComplete:true, official citations and no findings. These are outputs of trusted server code, never fields the browser is allowed to assert. The wrapper checks expiration again after review; a review that outlives its source snapshot is unavailable.

### Safe clarification response
When an applicable policy is pending, evidence conflicts or legal coverage is insufficient, return HTTP 200 Answer with status:needs_clarification and an explanation of the missing check. Do not include the unreviewed legal advice anyway and hope the status will hide it: the frontend renders clarification text as well. Omit unsafe calculations and unrelated citations. Set compliance to pending/conflict/unavailable as appropriate.

${code({data:{id:'answer-example',threadId:'thread-example',answer:'The applicable policy is awaiting legal review. Please request a review before relying on its terms.',status:'needs_clarification',citations:[],calculations:[],activity:[{label:'Legal review is pending',status:'attention'}],compliance:{status:'pending',state:'NC'}}},'Illustrative complete clarification envelope')}
`);

add('15 / Manual HTTP walkthrough: curl',`
These examples are for a development/test backend, not credentials to paste into production. Replace IDs and the base URL with records from your own authorized workspace. On Windows PowerShell, use curl.exe so the command is not treated as an Invoke-WebRequest alias. For cross-origin testing, the Origin below must be allowed by your server.

### Step 1: prepare request files
Create login.json with a real test account and property.json with the registration fields shown in E11. Do not commit real credentials. The OpenAPI and integration examples provide the exact shapes. Keep private test files out of shared archives.

### Step 2: establish a cookie session
${code('BASE="http://localhost:8001/api/v1"\nUI="http://localhost:5174"\ncurl --silent --show-error --include \\\n  -c cookies.txt -b cookies.txt \\\n  "$BASE/auth/session"\n\ncurl --silent --show-error \\\n  -c cookies.txt -b cookies.txt \\\n  -H "Origin: $UI" \\\n  -H "Content-Type: application/json" \\\n  --data-binary @login.json \\\n  "$BASE/auth/login" > login-response.json','POSIX shell; inspect the returned HTTP/body before proceeding')}

### Step 3: use the returned CSRF token
${code('CSRF=$(node -p \\\n  "JSON.parse(require(\'fs\').readFileSync(\'login-response.json\',\'utf8\')).data.csrfToken")\n\ncurl --silent --show-error --include \\\n  -b cookies.txt "$BASE/workspace"\n\ncurl --silent --show-error --include \\\n  -b cookies.txt -H "Origin: $UI" \\\n  -H "X-CSRF-Token: $CSRF" \\\n  -H "Content-Type: application/json" \\\n  --data-binary @property.json "$BASE/properties"','Keep the token in your test environment; do not publish it')}

### Step 4: upload a real policy
${code('curl --silent --show-error --include \\\n  -b cookies.txt -H "Origin: $UI" \\\n  -H "X-CSRF-Token: $CSRF" \\\n  -F "file=@rules.pdf;type=application/pdf" \\\n  -F "title=Maintenance policy" \\\n  -F "category=maintenance" \\\n  -F "propertyId=REPLACE_WITH_REAL_PROPERTY_ID" \\\n  -F "state=NC" -F "effectiveFrom=2026-11-15" \\\n  "$BASE/policies"','Use a valid effective date at execution time; do not set the multipart Content-Type header yourself')}

For a new version, send file, familyId, expectedVersion, state and effectiveFrom instead of changing the family's title/category/scope. Re-read the current workspace before choosing expectedVersion. Inspect status and JSON on every call; a shell command completing is not proof of HTTP success. Curl cannot verify browser cookie/CORS behavior.
`);

add('16 / Manual HTTP walkthrough: PowerShell',`
### JSON calls with a shared WebRequestSession
This uses standard PowerShell JSON request/session handling. Supply your backend address and credentials in a private login.json file; the response retains the browser-equivalent session cookies in the web variable.

${code('$base = "http://localhost:8001/api/v1"\n$ui = "http://localhost:5174"\n$loginBody = Get-Content -LiteralPath login.json -Raw\n\n$login = Invoke-RestMethod -Method Post `\n  -Uri "$base/auth/login" `\n  -ContentType "application/json" `\n  -Headers @{ Origin = $ui } `\n  -Body $loginBody -SessionVariable web\n\n$csrf = $login.data.csrfToken\n$headers = @{\n  Origin = $ui\n  "X-CSRF-Token" = $csrf\n}\n\n$workspace = Invoke-RestMethod -Method Get `\n  -Uri "$base/workspace" -WebSession $web\n\n$propertyBody = @{\n  name = "Oak House"\n  address = "10 Oak Street"\n  city = "Raleigh, NC 27601"\n  state = "NC"\n  units = 2\n} | ConvertTo-Json\n\n$created = Invoke-RestMethod -Method Post `\n  -Uri "$base/properties" -WebSession $web `\n  -Headers $headers -ContentType "application/json" `\n  -Body $propertyBody','PowerShell; HTTP errors must be inspected rather than ignored')}

### Multipart calls
PowerShell 7 supports Invoke-RestMethod -Form with a Get-Item file value. Windows PowerShell 5.1 does not provide the same -Form interface; use the API Explorer or curl.exe for multipart uploads. Do not mix a PowerShell WebRequestSession cookie store with an unrelated curl cookie jar and assume they share authentication. Use one client/session end-to-end.

### Get real identifiers from the read model
Use $workspace.data.properties, leases, requests and policies. A policy's id identifies one immutable revision; familyId identifies its version series. Never substitute a familyId into a DELETE revision path, and never treat a tenant user ID as a lease ID.
`);

add('17 / Acceptance matrix and test evidence',`
${table(['Area','Required positive test','Required negative/boundary test'],[
 ['Session','Both roles log in; refresh restores session; logout invalidates it.','Anonymous session is 200/null; expired protected access is 401.'],
 ['Isolation','Tenant sees only their lease/property; landlord sees own organization.','Foreign lease/thread/request/document IDs disclose no other account data.'],
 ['Registration','NC property creates a complete Property DTO.','Tenant write, missing state, TX state, zero/fractional units fail.'],
 ['CORS / cookies','Browser login + credentialed GET/POST work for allowed origin.','Disallowed origin, bad CSRF and missing cookie fail safely.'],
 ['Policy upload','Native-text PDF returns durable pending metadata.','Empty/non-PDF/oversized file, bad state and unavailable property fail.'],
 ['Versioning','Replacement updates predecessor boundary atomically.','Two writers with same expectedVersion: one success, one 409.'],
 ['Date filter','Before/at effective boundary selects exactly one version.','Pending/failed replacement does not resurrect expired content.'],
 ['Cancellation','Latest staged future pending revision can be canceled.','Effective, ready, historical and superseded versions are immutable.'],
 ['Legal review','Exact document/answer/scope/date receives current trusted assessment.','Wrong hash/date/state/scope, expired review, unknown citations or findings block use.'],
 ['Assistant','Citations and cent calculations match authorized evidence.','Unclear/conflicting/unready evidence returns safe clarification.'],
 ['Requests','Tenant creates; owning landlord replies; tenant sees update.','Other tenants/organizations cannot read or reply.'],
 ['Failure handling','Safe JSON errors preserve requestId and field details.','HTML/204/raw DTO/API outage do not silently activate mock mode.']])}

### Record evidence, not just checkmarks
For each environment, retain contract version, backend build identifier, applied API base, account roles, scenario/date, status/result and relevant server request IDs. Use non-production test documents and redact tenant/credential data. The explorer report deliberately excludes bodies, passwords and tokens; it is structural evidence, not a complete security/legal test report.

Run npm test and npm run build in the frontend repository. Run python -m unittest discover -s tests -v for the reusable cache/review boundary. Add backend endpoint tests and run browser/application acceptance against your actual service; existing fixtures are not tests of your deployed backend.
`);

add('18 / Production cutover and rollback',`
### Pre-cutover checklist
1. Freeze the accepted OpenAPI contract and record its version/hash with the backend release.
2. Provision production roles/organizations/properties and verify NC state associations without demo records.
3. Confirm private file storage, extraction/indexing jobs, legal-source freshness monitoring and reviewer availability.
4. Configure TLS, trusted proxy headers, cookie flags, CSRF/origin checks and CORS/CSP where required.
5. Set the application build environment to api mode and the chosen base, build, deploy and inspect the generated asset release.
6. Validate session -> workspace -> lease -> request/reply -> policy lifecycle -> assistant flows using both roles on the actual deployed topology.
7. Restrict developer tooling to the intended testing audience or remove its entry point according to the release plan. Hiding a toggle alone does not protect /api-docs/.

### No automatic promotion
Applying a server in the explorer does not update the application. A successful test report does not deploy it. VITE_* values are baked into the built frontend, so changes require rebuilding/redeploying. LAGA_API_PROXY only affects the development server.

### Release/rollback behavior
Keep a known-good frontend asset release and backend release identifier. Roll back compatible deployments deliberately; do not alter effective policy history to compensate for a failed release. If a legal reviewer/source is unavailable, keep affected guidance blocked rather than switching users to mock data or a previous expired policy.

### Operational ownership
Assign owners for session failures, API availability, ingestion failures, source refresh failures, review conflicts and retrieval integrity. Attach request IDs to safe logs; do not log passwords, CSRF tokens, raw tenant documents or private model reasoning. Define your retention, deletion, incident response and legal review service levels before production; this API version does not prescribe numerical SLAs.
`);

add('19 / Troubleshooting by symptom',extract(connection,'## Troubleshooting')+`

### Additional integration checks
${table(['Symptom','Likely cause / correction'],[
 ['A create route is successful but explorer flags status','Backend returned 201; this contract specifies 200. Align the backend or coordinate a contract/UI change.'],
 ['Login works in curl, not browser','Curl does not enforce CORS, SameSite, mixed-content or third-party cookie policy. Inspect browser requests.'],
 ['New version fails enum validation','Omit inapplicable multipart fields; do not send literal undefined/null strings. Existing family scope/category/state remain fixed.'],
 ['Policy is ready but not eligible','Ingestion readiness and legal review are separate; inspect current compliance and exact contentHash/scope/date.'],
 ['Review passes for yesterday but not today','The wire guard requires exact asOf. Refresh/reassess using date-appropriate source coverage. Do not fabricate a new date on an old verdict.'],
 ['Review expires while model/reviewer is running','Reference boundary blocks it. Refresh the snapshot and rerun the assessment, subject to rate/retry policy.'],
 ['Official source URL redirects','Reference fetcher rejects redirects. Verify and update the trusted source configuration; do not approve an HTML redirect/challenge page.'],
 ['Developer Tools is absent on a lease page','Intentional: use login or home dashboard; the direct /api-docs/ route remains available.'],
 ['An example review immediately fails','Fixed fictional timestamps may be expired. Generate a fresh genuine review; do not use fixture approvals in production.'],
 ['Upload canceled but a version appears','Browser cancel does not roll back server work. Refresh and reconcile the actual accepted version before retrying.']])}
`);

add('20 / Decisions to close before implementation',`
The following details are not invented by this handbook. The integration owner should record the chosen implementation alongside the release so the frontend and backend teams have one agreement.

${table(['Decision','Owner / required outcome'],[
 ['Backend runtime and deployment','Backend + hosting: framework, base URL, environments, reachable upstream and health/monitoring approach.'],
 ['Tenant/landlord account provisioning','Backend/product: identity provider, registration/password recovery and lease association workflow. No signup/provisioning endpoints are in this API version.'],
 ['Unassigned tenant behavior','Product + frontend/backend: provision the lease association and verify the existing home empty state plus any other lease-dependent controls.'],
 ['Canonical policy text','Ingestion owner: exact extracted-text representation/UTF-8 bytes and hash persistence; preserve original PDF checksum too.'],
 ['Legal reviewer and coverage','Legal/compliance + backend: qualified reviewer, applicable exceptions/amendments/federal/local coverage and unsupported-date policy.'],
 ['Findings object shape','Current schema permits object findings; UI renders message or description. Standardize clause/section details internally; extra presentation fields require coordination.'],
 ['Retry/idempotency strategy','Backend: safe mutation recovery after timeouts. No Idempotency-Key or public job/retry endpoint is specified.'],
 ['Retention and access audit','Security/operations: immutable version and cancellation audit, private storage retention and incident ownership.'],
 ['Future contract extensions','Joint owner: pagination, streaming, job progress, document downloads, multi-state support or a new factual-answer exemption require coordinated schemas/adapter work.']])}

### Compatibility rule
Do not replace an established response shape with your database model or add undeclared top-level fields. Additive optional fields, new routes or changed status codes still need contract and adapter review. Keep the spec, behavioral guide, examples, explorer and backend tests synchronized.

### What is not promised
There is no automated production connection, no included production database/RAG backend, no guarantee that a source snapshot is a complete statement of applicable law, and no legal certification from a successful HTTP/schema check. These are implementation and acceptance responsibilities, not missing URL settings.
`);

const meaning={
 id:'Opaque stable identifier. Authorize the underlying object independently of its format.',name:'Human-readable name; never use as the authorization key.',email:'Account email returned by the server; login accepts email/password only.',role:'Wire role. The UI label Customer corresponds to tenant.',permissions:'Server-issued permission strings used for UI visibility; server checks remain mandatory.',organization:'Display organization name, not proof of membership.',propertyId:'Authorized property association. A nullable policy scope of null means organization-wide within its state.',leaseId:'Authorized lease association; never accept a foreign tenant lease.',tenantId:'Owning tenant identity; derive/validate against authenticated scope.',unit:'Display unit identifier; a string, not necessarily a number.',state:'Jurisdiction code. NC is the only configured state in this contract.',csrfToken:'Opaque CSRF token returned with session data; held in page memory, sent on authenticated mutations.',user:'Authenticated user, or null in an anonymous Session.',asOf:'Requested/server business calendar date. Exact matching matters for review identity.',timeZone:'IANA time zone for date interpretation/display; configure real business rules, not fixture values.',demo:'Optional preview marker. Real production behavior must not depend on demo fixtures.',size:'Uploaded file size in bytes.',pageCount:'PDF page count; required but nullable while unknown.',status:'Lifecycle/result state; see the model-specific enum and behavioral chapters.',familyId:'Stable identity across immutable policy versions; not a revision/document ID.',version:'Monotonically increasing positive integer within a policy family.',expectedVersion:'Optimistic concurrency token: latest known version before appending a revision.',effectiveFrom:'Inclusive calendar date at which this version applies.',effectiveTo:'Exclusive end boundary; null means open-ended.',supersedesId:'Previous immutable revision ID when one exists.',uploadedAt:'Server timestamp with UTC offset; separate from effectiveFrom.',uploadedBy:'Uploader display name returned by the server; audit identity must be retained internally.',description:'Display description; also used as a fallback for a review finding.',excerpt:'Searchable/source excerpt; nullable while unavailable. Not a canonical full-document hash input.',contentHash:'SHA-256 lowercase hex of exact reviewed content; match canonical policy text or final answer as specified.',checkedAt:'Timestamp when this review was checked; must not be in the future.',expiresAt:'Exclusive expiration instant for the review/source snapshot.',lawRevision:'Content-derived law snapshot revision. Backend must bind it to current applicable coverage.',kind:'Review target: policy or answer.',scopeKey:'Exact review scope key; backend must also bind organization/object ownership.',findings:'Review findings. A passed review cannot carry unresolved findings.',citations:'Evidence references. Answer citations and legal-review citations are different models.',url:'Official law/guidance URL; current metadata allowlist is exact.',section:'Source section identifier; nonempty for legal-review citations.',quote:'Exact authorized source excerpt used to substantiate an answer.',documentId:'Stable document/revision identity. Policy references must name the actual version.',page:'Source page number; null when page mapping is unavailable.',question:'User question, 1–2000 characters; validate scope and evidence independently.',scope:'Requested lease or portfolio context; server authorizes it.',threadId:'Conversation identity; optional/nullable on input, required on output. Never an access token.',answer:'Final displayed text. If supported, the exact UTF-8 string must match its review hash.',calculations:'Deterministic calculation records; server validates inputs/method/results before release.',activity:'User-safe check labels; never private model chain-of-thought.',inputs:'Named integer/string/boolean calculation inputs; monetary inputs use integer cents.',result:'Integer calculation result in USD cents.',currency:'USD in the current contract.',method:'Human-readable calculation method; never execute a client expression.',label:'User-visible activity/calculation label.',category:'Policy enum for policies; free-form string for clarification requests.',subject:'Clarification subject; enforce the schema length limit.',message:'Clarification body or safe validation detail, depending on model.',reply:'Landlord reply; null for an unanswered Request.',createdAt:'Server creation timestamp with offset.',signedOut:'True on a successful logout.',deleted:'True on a successful staged-version cancellation.',error:'Error envelope; no data property on failures.',code:'Stable machine-readable error code; keep it safe and actionable.',requestId:'Server correlation ID safe to share for diagnostics.',fields:'Map of field names to safe human-readable validation messages.',rent:'Contracted monthly rent in integer USD cents.',deposit:'Security deposit in integer USD cents.',startDate:'Lease start calendar date.',endDate:'Lease end calendar date; does not by itself determine statutory notice rights.',dueDay:'Contractual rent-due day; validate legal applicability separately.',noticeDays:'Contractual notice period; not an independent legal ruling.',paymentStatus:'UI ledger state; do not invent amounts from this label.',renewalStatus:'Backend renewal workflow display status.',documents:'Lease document IDs; no download route is specified yet.',address:'Street address display field.',city:'City/ZIP display string in the existing UI; not a separate state source.',units:'Integer number of property units.',style:'Required frontend illustration key; use a supported default.',amenities:'Display amenity strings; an empty array is allowed.',properties:'Authorized property records (or a property count in Summary).',leases:'Authorized lease records.',tenants:'Authorized tenant User records only.',requests:'Authorized clarification requests.',policies:'Policy version records, including readiness and compliance metadata.',summary:'Aggregates computed from the same authorized lease/property set.',occupied:'Occupied home count; avoid double counting shared leaseholders.',monthlyRent:'Authorized active contracted monthly rent total in cents.',outstandingRent:'Authorized outstanding ledger amount in cents.',renewals:'Leases meeting the current renewal window in the read model.',title:'Document/source/policy title. Fixed across an existing policy family.',password:'Credential input only; never return or log it.',type:'Scope discriminator: lease or portfolio.',clauses:'Authorized source Citation records for the selected lease.',lease:'The authorized structured lease.',property:'Property associated with the selected lease.',tenant:'Tenant associated with the selected lease.'
};
function typeOf(schema){if(schema.$ref)return schema.$ref.split('/').at(-1);if(schema.const!==undefined)return JSON.stringify(schema.const);if(schema.enum)return [...new Set(schema.enum.map(v=>v===null?'null':typeof v))].join(' | ');if(schema.type==='array')return 'array<'+typeOf(schema.items)+'>';return Array.isArray(schema.type)?schema.type.join(' | '):schema.type||'object'}
function constraints(schema){return [schema.enum?'Allowed: '+schema.enum.join(', '):'',schema.const!==undefined?'Constant: '+JSON.stringify(schema.const):'',schema.minLength!==undefined?'Min length '+schema.minLength:'',schema.maxLength!==undefined?'Max length '+schema.maxLength:'',schema.minimum!==undefined?'Min '+schema.minimum:'',schema.maximum!==undefined?'Max '+schema.maximum:'',schema.pattern?'Pattern: '+schema.pattern:'',schema.format?'Format: '+schema.format:'',schema.additionalProperties&&typeof schema.additionalProperties==='object'?'Additional values: '+typeOf(schema.additionalProperties):''].filter(Boolean).join('; ')}
const modelGroups=[['A1 / Identity and session models',['User','Session']],['A2 / Properties and workspace',['PropertyRegistration','Property','Summary','Workspace']],['A3 / Leases, details and question scope',['Lease','LeaseDetail','Scope']],['A4 / Policy upload and immutable versions',['PolicyUpload','PolicyVersion']],['A5 / Assistant requests and evidence',['AskInput','Answer','Citation','Calculation','Activity']],['A6 / Clarification request workflow',['RequestInput','Request','ReplyInput']],['A7 / Compliance review metadata',['Compliance','LawCitation']],['A8 / Errors and mutation acknowledgments',['ErrorDetails','Error','Deleted','Logout','LoginInput']]];
for(const [title,names] of modelGroups){
 let body='<p>Generated from the current OpenAPI schemas. Required means the key must be present; nullable means null is permitted as a value. Semantic/backend checks still apply.</p>';
 for(const name of names){const schema=spec.components.schemas[name];body+=`<h3 id="model-${name}">${name}</h3><p class="model-note">Additional undeclared properties: <strong>${schema.additionalProperties===false?'rejected':'allowed as defined by schema'}</strong>.</p>`;
 body+=table(['Field','Type / required','Meaning / constraints'],Object.entries(schema.properties||{}).map(([field,definition])=>['`'+field+'`',typeOf(definition)+' · '+(schema.required?.includes(field)?'Required':'Optional'),(meaning[field]||'See the model and endpoint behavior for usage.')+(constraints(definition)?' '+constraints(definition)+'.':'')])).replace('<table>','<table><caption>'+name+' fields</caption>');
 if(name==='Scope')body+='<p class="callout">Server invariant: type lease requires a nonempty authorized lease id; portfolio uses id:null and landlord authorization. The base schema does not enforce this cross-field rule.</p>';
 if(name==='PolicyUpload')body+='<p class="callout">Conditional requirement: familyId present -> expectedVersion required; no familyId -> title and category required. file, state and effectiveFrom are always required. Binary file data is a multipart part, not a JSON placeholder.</p>';
 if(name==='Compliance')body+='<p class="callout">When status is passed, state, kind, scopeKey, asOf, checkedAt, expiresAt, lawRevision, contentHash and citations are all required. State must be NC, hashes must be 64 lowercase hex characters, citations cannot be empty, and findings must be absent/empty. Runtime checks additionally verify dates, scope, identity and source applicability.</p>';
 }
 add(title,body,{group:'Complete data dictionary',html:true});
}
const documentedModels=new Set(modelGroups.flatMap(([,names])=>names));
if(Object.keys(spec.components.schemas).some(name=>!documentedModels.has(name)))throw Error('A model is missing from the dictionary.');

const guideExamples={
 anonymousSession:{schema:'Session',value:{user:null,csrfToken:null}},
 authenticatedSession:{schema:'Session',value:fullExamples.session.data},
 registeredProperty:{schema:'Property',value:fullExamples.workspace.data.properties[0]},
 emptyLandlordWorkspace:{schema:'Workspace',value:{asOf:'2026-10-31',timeZone:'America/New_York',user:fullExamples.session.data.user,properties:[],leases:[],tenants:[],requests:[],policies:[],summary:{properties:0,units:0,occupied:0,monthlyRent:0,outstandingRent:0,renewals:0}}},
 pendingPolicy:{schema:'PolicyVersion',value:{id:'document-example-v1',familyId:'family-example',title:'Maintenance policy',name:'rules.pdf',category:'maintenance',propertyId:'property-example',state:'NC',status:'processing',compliance:{status:'pending',state:'NC'},version:1,effectiveFrom:'2026-11-15',effectiveTo:null,uploadedAt:'2026-10-31T12:00:00Z',size:2048,pageCount:null,uploadedBy:'Alex Morgan',description:'Document processing and legal review are pending.',excerpt:null}},
 clarificationAnswer:{schema:'Answer',value:{id:'answer-example',threadId:'thread-example',answer:'The applicable policy is awaiting legal review. Please request a review before relying on its terms.',status:'needs_clarification',citations:[],calculations:[],activity:[{label:'Legal review is pending',status:'attention'}],compliance:{status:'pending',state:'NC'}}},
 syntheticReviewedAnswer:{schema:'Answer',value:examples.illustrativePassedAnswer.data},
 versionConflict:{schema:'Error',value:{error:{code:'VERSION_CONFLICT',message:'This policy changed. Refresh the library before adding a version.',requestId:'example-request',fields:{expectedVersion:'The latest version is 3.'}}}}
};
for(const [name,{schema,value}] of Object.entries(guideExamples)){
 add('J / '+name+' — '+schema,`<p>Complete ${esc(schema)} example. Fictional identifiers, accounts and fixed timestamps are illustrative. Do not use these as production records or approvals. Generate fresh genuine review metadata for live checks.</p>`+code(schema==='Error'?value:{data:value},'Exact JSON response envelope')+(name==='syntheticReviewedAnswer'?'<p class="callout">This is a structural test fixture, not an actual legal assessment. Its lawRevision is a placeholder, its text is illustrative, and its fixed timestamps expire. The contentHash matches only the exact example answer string.</p>':''),{group:'Worked JSON responses',html:true});
}

add('21 / References, version and handoff receipt',`
### Contract snapshot
API contract version: ${spec.info.version}. OpenAPI dialect: ${spec.openapi}. Prepared October 31, 2026. All dates/IDs/credentials in worked examples are illustrative; generate current genuine review metadata and use your own authorized data.

${code(hash,'SHA-256 of contracts/openapi.json used to generate this PDF')}

### External references
- [Vite environment replacement](https://vite.dev/guide/env-and-mode)
- [Vite development proxy](https://vite.dev/config/server-options.html#server-proxy)
- [Browser CORS and credential behavior](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS)
- [Nginx upstream URI forwarding](https://nginx.org/en/docs/http/ngx_http_proxy_module.html#proxy_pass)
- [Configured NC General Assembly law source](https://www.ncleg.gov/EnactedLegislation/Statutes/HTML/ByChapter/Chapter_42.html)
- [Configured NC Department of Justice guidance](https://ncdoj.gov/protecting-consumers/home-repair-and-products/renting-a-home/)

### Handoff receipt to complete
${table(['Record','Value to fill by the integration team'],[['Backend release / contract version','________________________________________'],['Development / staging / production API base','________________________________________'],['Chosen browser topology and frontend origin','________________________________________'],['Test account provisioning owner','________________________________________'],['Ingestion / review / operational owner','________________________________________'],['Explorer report and backend test evidence','________________________________________'],['Application acceptance / release approval','________________________________________']])}

### Regeneration and scope
This document is generated from authored integration guidance plus the repository's actual OpenAPI schemas and behavior. Rebuild it whenever the contract or adapter changes. The original repository retains editable source and a build manifest. The companion documentation ZIP contains this PDF, the OpenAPI file, example payloads and connection/behavioral guides.
`,{group:'Release reference'});

const css=`
@font-face{font-family:Manrope;src:url('../node_modules/@fontsource-variable/manrope/files/manrope-latin-wght-normal.woff2') format('woff2');font-weight:200 800}*{box-sizing:border-box}html{background:#e9e7ef}body{margin:0;font-family:Manrope,'Segoe UI',sans-serif;color:#302c44;font-size:10pt;line-height:1.55}.page{width:8.5in;height:11in;padding:.78in .65in .65in;background:white;position:relative;margin:20px auto;overflow:hidden;break-after:page;page-break-after:always}.page:last-child{break-after:auto;page-break-after:auto}.page-body{height:9.52in;overflow:visible}.running-head{position:absolute;top:.27in;left:.65in;right:.65in;display:flex;align-items:center;justify-content:space-between;padding-bottom:8px;border-bottom:1px solid #e9e3f0;color:#9b8da8;font-size:7.3pt;letter-spacing:.035em}.running-head b{color:#605084;font-size:11pt;letter-spacing:-.02em}.footer{position:absolute;left:.65in;right:.65in;bottom:.27in;border-top:1px solid #e9e3f0;display:flex;justify-content:space-between;padding-top:9px;font-size:7pt;color:#95839f}.section-label{font-size:7.5pt;letter-spacing:.13em;text-transform:uppercase;color:#9b7cb1;margin:0 0 10px}h1{font-size:23pt;line-height:1.25;letter-spacing:-.035em;margin:0 0 20px;color:#3a3050}h2{font-size:16pt;letter-spacing:-.025em}h3{font-size:11.3pt;line-height:1.35;letter-spacing:-.01em;margin:20px 0 8px;color:#65517d}p{margin:0 0 12px}ul,ol{padding-left:21px;margin:0 0 14px}li{padding-left:3px;margin-bottom:7px}strong{font-weight:750}code,pre{font-family:Consolas,'Courier New',monospace}code{font-size:.88em;background:#f4f0f8;border-radius:3px;padding:1px 3px;overflow-wrap:anywhere}pre{margin:0 0 14px;padding:13px 15px;border:1px solid #e9e2f1;border-radius:7px;background:#f8f5fb;font-size:8pt;line-height:1.6;white-space:pre-wrap;overflow-wrap:anywhere;tab-size:2;color:#51435e}.code-caption{font-size:7.6pt;font-weight:700;color:#9a7bad;margin:10px 0 5px}.model-note{font-size:8pt;color:#95869f;margin-bottom:9px}table{width:100%;border-collapse:collapse;table-layout:fixed;font-size:8pt;line-height:1.5;margin:12px 0 16px}th{text-align:left;background:#eee8f6;color:#79618c;font-weight:750;font-size:7.6pt}td,th{padding:8px 9px;border:1px solid #e7e0ed;vertical-align:top;overflow-wrap:anywhere}td:first-child{font-weight:650;color:#6d547f}tr:nth-child(even) td{background:#fcfafd}td code{padding:0;background:none;font-size:7.8pt}a{color:#775696;text-decoration:none;overflow-wrap:anywhere}.callout{background:#f5effa;border-left:3px solid #a588bc;border-radius:4px;padding:12px 14px;font-size:8.7pt}.endpoint-badge{display:inline-block;padding:4px 9px;border-radius:5px;font:700 9pt Consolas,monospace;letter-spacing:.05em;background:#eee7f7;color:#7d5a9a}.endpoint-badge.get{background:#eaf3ee;color:#57866f}.endpoint-badge.delete{background:#fbefeb;color:#b27b6a}.endpoint-path{font:12pt/1.6 Consolas,monospace;color:#755985;margin:10px 0 18px;overflow-wrap:anywhere}.cover{background:linear-gradient(145deg,#fcfafe,#f1ebf9);padding:.8in .75in}.cover .page-body{height:9.3in}.cover-logo{font-size:36pt;font-weight:800;letter-spacing:-.07em;color:#514285;margin-bottom:14px}.cover-logo span{color:#ae8ec2}.cover-tag{font-size:9pt;letter-spacing:.15em;color:#9a7daf;margin-top:38px}.cover h1{font-size:40pt;line-height:1.16;margin:24px 0;color:#3c2f54;max-width:560px}.cover h1 span{color:#9270a7}.cover-deck{font-size:13pt;color:#8f789f;max-width:520px;line-height:1.75;margin-bottom:35px}.cover-meta{display:grid;grid-template-columns:1fr 1fr;gap:16px;background:#ffffffbb;border:1px solid #dfd3eb;border-radius:12px;padding:22px;margin:30px 0}.cover-meta small{font-size:7.5pt;letter-spacing:.09em;color:#a087ae;display:block;text-transform:uppercase}.cover-meta strong{display:block;font-size:11pt;margin-top:6px}.cover-note{font-size:9pt;color:#927e9f;line-height:1.8;border-top:1px solid #dfd2eb;padding-top:20px;max-width:560px}.contents-grid{display:grid;grid-template-columns:1fr 1fr;gap:25px}.contents-group h3{font-size:9pt;text-transform:uppercase;letter-spacing:.06em;margin:15px 0 8px}.contents-item{display:flex;gap:9px;justify-content:space-between;align-items:baseline;border-bottom:1px solid #f0eaf4;padding:6px 0;font-size:8.3pt;line-height:1.45}.contents-item span{flex:1}.contents-item b{font-size:8pt;color:#9e81b0}.contents-intro{font-size:9pt;color:#9581a2;margin-bottom:18px}.continued{color:#b39bc0;font-size:10pt;font-weight:450}.small-note{font-size:8pt;color:#9b88a7}caption{text-align:left;font-size:9pt;font-weight:750;color:#826394;padding:7px 0}body{line-height:1.47}p{margin-bottom:10px}h1{margin-bottom:16px}h3{margin-top:16px}li{margin-bottom:6px}table{line-height:1.42}td,th{padding:7px 8px}pre{line-height:1.48}@page{size:Letter;margin:0}@media print{html{background:white}.page{margin:0;box-shadow:none}a{color:inherit}body{print-color-adjust:exact;-webkit-print-color-adjust:exact}}
`;

const pagination=String.raw`
const sections=JSON.parse(document.getElementById('book-data').textContent);
function page(title,group,id,continued=false){const el=document.createElement('section');el.className='page';if(id)el.id=id;el.innerHTML='<header class="running-head"><b>laga.</b><span>BACKEND INTEGRATION · CONTRACT '+document.body.dataset.version+'</span></header><div class="page-body"><div class="section-label">'+group+'</div><h1>'+title+(continued?' <span class="continued">/ continued</span>':'')+'</h1></div><footer class="footer"><span>Lease Agreement Guard Agent · Integration handbook</span><span class="page-number"></span></footer>';document.body.append(el);return el.querySelector('.page-body')}
function fits(body){return body.scrollHeight<=body.clientHeight+1}
function makeContinuation(section){return page(section.title,section.group,null,true)}
function paginate(section){let body=page(section.title,section.group,section.id);for(const child of [...new DOMParser().parseFromString(section.html,'text/html').body.children]){
 if(child.tagName==='TABLE'){let table=child.cloneNode(false);table.innerHTML=(child.caption?.outerHTML||'')+child.tHead?.outerHTML+'<tbody></tbody>';body.append(table);for(const row of [...child.tBodies[0].rows]){table.tBodies[0].append(row);if(!fits(body)){row.remove();if(!table.tBodies[0].rows.length)table.remove();body=makeContinuation(section);table=child.cloneNode(false);table.innerHTML=(child.caption?.outerHTML||'')+child.tHead?.outerHTML+'<tbody></tbody>';body.append(table);table.tBodies[0].append(row);if(!fits(body))throw Error('Oversized table row in '+section.title)}}continue}
 if(child.tagName==='PRE'){const lines=child.textContent.split('\n');let pre=document.createElement('pre');body.append(pre);for(const line of lines){const before=pre.textContent;pre.textContent+=(pre.textContent?'\n':'')+line;if(!fits(body)){pre.textContent=before;if(!before)pre.remove();body=makeContinuation(section);pre=document.createElement('pre');pre.textContent=line;body.append(pre);if(!fits(body))throw Error('Oversized code in '+section.title)}}continue}
 if(['UL','OL'].includes(child.tagName)){let list=child.cloneNode(false),counter=1;body.append(list);for(const item of [...child.children]){list.append(item);if(!fits(body)){item.remove();if(!list.children.length)list.remove();body=makeContinuation(section);list=child.cloneNode(false);if(list.tagName==='OL')list.start=counter;body.append(list);list.append(item)}counter++}continue}
 // Keep a new subheading with a useful amount of following content.
 if(child.tagName==='H3'&&body.clientHeight-(body.lastElementChild?.getBoundingClientRect().bottom-body.getBoundingClientRect().top)<110)body=makeContinuation(section);
 body.append(child);if(!fits(body)){child.remove();body=makeContinuation(section);body.append(child);if(!fits(body))throw Error('Oversized block in '+section.title)}
 }}
async function build(){await document.fonts.ready;for(const section of sections)paginate(section);const pages=[...document.querySelectorAll('.page')];for(let i=0;i<pages.length;i++)pages[i].querySelector('.page-number').textContent=String(i+1).padStart(2,'0')+' / '+pages.length;
 const first=document.querySelector('#contents-left'),second=document.querySelector('#contents-right'),third=document.querySelector('#contents-json');for(const [group,target]of [['Implementation',first],['Endpoint reference',second],['Complete data dictionary',second],['Worked JSON responses',third],['Release reference',first]]){const box=document.createElement('div');box.className='contents-group';box.innerHTML='<h3>'+group+'</h3>';for(const section of sections.filter(s=>s.group===group)){const index=pages.indexOf(document.getElementById(section.id))+1;const item=document.createElement('a');item.className='contents-item';item.href='#'+section.id;item.innerHTML='<span>'+section.title+'</span><b>'+index+'</b>';box.append(item)}target.append(box)}
 const overflows=pages.map((p,i)=>({page:i+1,title:p.querySelector('h1')?.textContent,scroll:p.querySelector('.page-body').scrollHeight,height:p.querySelector('.page-body').clientHeight})).filter(p=>p.scroll>p.height+1);window.bookResult={pageCount:pages.length,sections:sections.length,overflows,models:document.body.dataset.models};window.bookReady=true;if(overflows.length)throw Error('Overflow: '+JSON.stringify(overflows))}
build().catch(error=>{window.bookError=error.message;console.error(error)});
`;
const cover=`<section class="page cover" id="cover"><div class="page-body"><div class="cover-logo">laga<span>.</span></div><p class="small-note">Lease Agreement Guard Agent</p><div class="cover-tag">BACKEND IMPLEMENTATION & HANDOFF</div><h1>One clear path<br/>from API contract<br/><span>to connected app.</span></h1><p class="cover-deck">An implementation handbook for backend engineers, integration testers and deployment owners. Includes the complete endpoint and DTO reference.</p><div class="cover-meta"><div><small>Contract</small><strong>${spec.info.version} · OpenAPI ${spec.openapi}</strong></div><div><small>Prepared</small><strong>October 31, 2026</strong></div><div><small>Initial jurisdiction</small><strong>North Carolina · NC</strong></div><div><small>Integration surface</small><strong>${ops.length} endpoints · ${Object.keys(spec.components.schemas).length} models</strong></div></div><p class="cover-note">Start with the implementation route. Use the endpoint pages while building, the field dictionary while mapping DTOs, and the acceptance matrix before switching the application to API mode.<br/><br/>This is an integration target and engineering handoff, not a deployed backend or a legal compliance certification.</p></div><footer class="footer"><span>Implementation handbook · Documentation revision 1</span><span class="page-number"></span></footer></section>`;
const toc=`<section class="page" id="contents"><header class="running-head"><b>laga.</b><span>BACKEND INTEGRATION · CONTRACT ${spec.info.version}</span></header><div class="page-body"><div class="section-label">NAVIGATION</div><h1>Find what you need.</h1><p class="contents-intro">Read the implementation chapters in order on the first pass. Return to the endpoint and model reference for exact wire details. Section links are clickable.</p><div class="contents-grid"><div id="contents-left"></div><div id="contents-right"></div></div></div><footer class="footer"><span>Lease Agreement Guard Agent · Integration handbook</span><span class="page-number"></span></footer></section>`;
const examplesContents=`<section class="page" id="contents-examples"><header class="running-head"><b>laga.</b><span>BACKEND INTEGRATION ? CONTRACT ${spec.info.version}</span></header><div class="page-body"><div class="section-label">COPYABLE RESPONSE REFERENCE</div><h1>Examples you can map<br/>directly to your service.</h1><p class="contents-intro">The JSON appendix contains complete response envelopes. It complements the route-specific request samples and the field dictionary.</p><div class="contents-grid"><div id="contents-json"></div><div><h3>How to read the examples</h3><p>Every ID, account and date is fictional. Copy the structure, not the sample authorization or verdict.</p><p>For the live backend, replace IDs with records returned by the current workspace and use a real test account for each role.</p><p>The passed-review example is synthetic. Its hash matches the example text only, its law revision is a placeholder, and its timestamps expire.</p><h3>Two different sample files</h3><p><code>contracts/integration-examples.json</code> contains request fixtures. <code>docs/integration-guide-examples.json</code> contains the response examples printed in this handbook.</p><h3>Required means present</h3><p>Keep required nullable fields present with null when unknown. Omit optional fields only when permitted. Extra undeclared object fields are rejected by most DTO schemas.</p></div></div><h3>Use the correct example for the task</h3><p>An empty landlord workspace is a valid bootstrap shape, not a substitute for a failed database read. A processing policy is durable accepted metadata, not ready evidence. A clarification answer is a safe supported workflow outcome when a legal check is missing; do not include unreviewed advice in its text.</p><p class="callout">Validate examples and real responses with the same OpenAPI version. The machine-readable spec remains authoritative for fields and envelopes; the implementation chapters explain ownership, date boundaries and security requirements that schemas cannot prove.</p></div><footer class="footer"><span>Lease Agreement Guard Agent ? Integration handbook</span><span class="page-number"></span></footer></section>`;
const output=path.join(root,`docs/Laga-Backend-Integration-Guide-v${spec.info.version}.html`);
const html=`<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Laga Backend Integration Guide ${spec.info.version}</title><meta name="author" content="Laga"><style>${css}</style></head><body data-version="${spec.info.version}" data-models="${Object.keys(spec.components.schemas).length}">${cover}${toc}${examplesContents}<script type="application/json" id="book-data">${JSON.stringify(sections).replace(/</g,'\u003c')}</script><script>${pagination}</script></body></html>`;
await fs.writeFile(output,html,'utf8');
await fs.writeFile(path.join(root,'docs/integration-guide-examples.json'),JSON.stringify(guideExamples,null,2)+'\n','utf8');
await fs.writeFile(path.join(root,'docs/integration-guide-manifest.json'),JSON.stringify({title:'Laga Backend Integration Guide',contractVersion:spec.info.version,prepared:'2026-10-31',specSha256:hash,endpointCount:ops.length,modelCount:Object.keys(spec.components.schemas).length,sections:sections.map(({id,title,group})=>({id,title,group})),source:'scripts/build-integration-guide.mjs'},null,2)+'\n');
console.log(JSON.stringify({html:output,sections:sections.length,endpoints:ops.length,models:Object.keys(spec.components.schemas).length,specSha256:hash}));

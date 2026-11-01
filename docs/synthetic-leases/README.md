# Synthetic tenant lease corpus

Ten fictional, unsigned North Carolina lease packets for backend ingestion and retrieval testing. Each packet has 12 native-text PDF pages, a matching Markdown copy, printable HTML and JSON expected extraction results. All four annexures are inside each packet, not separate files. Every authorized resident, including children, is named on the agreement cover, household roster, occupancy section, every annexure and the signature schedule. The primary tenant remains identified separately; listing a resident does not make them a signatory.

These are test documents, not legal lease forms or government-approved policies. No legal compliance review was performed. State-law verification being disabled in the app does not certify these documents. Do not use them for a real tenancy, payment or signature request.

## Start here

1. Read `manifest.json`. Its stable `documentId`, `leaseId`, `tenantId` and `propertyId` map directly to `frontend/src/data/fixtures.js`.
2. Ingest only the ten `.pdf` files as tenant lease documents. Alternatively, use `.md` for a plain-text ingestion path. Ingesting PDF, HTML and Markdown together would create duplicate evidence.
3. Attach each file to its manifest tenant, lease, property and NC state. Enforce tenant authorization independently. These are private lease fixtures, not organization-wide policy uploads; do not send them to `POST /policies`.
4. Compare extracted data with the same-stem `.json` file. This is an answer key, not a replacement production API DTO or new OpenAPI endpoint. Keep answer keys out of the retrieval index used to evaluate extraction.
5. Preserve section/page citations and annexure scope. The packet has section 3.1 on page 3, section 4.2 on page 4, section 8.1 on page 8 and section 12.1 on page 12, matching existing mock citation locations.

The API contract currently has no lease-upload route. The backend team should use its internal ingestion job or define and agree a lease-ingestion API before connecting an upload flow. Dropping these files into the repository does not seed a database or change mock gateway behavior.

## Coverage and interpretation

- Rents, deposits, names, IDs, properties, units and fixed-term dates come from the current frontend fixtures. All ten terms span 12 calendar months, with inclusive end dates; one starts mid-month.
- New fictional details include tenant age, occupation, personal income, adult/child household roster, smoking/vaping disclosures, pets, test banking details, telephone numbers and emergency contacts. Household totals include the named tenant. Ages are measured on the stated scenario agreement date, not today's date; no birth dates are inferred.
- Money is USD integer cents in JSON and formatted dollars in documents. Income is the named tenant's gross personal income, not household income. Annual income is monthly income multiplied by 12. Missing rates and charges are explicitly unspecified.
- Phone numbers use the reserved fictional `202-555-01xx` range. Emails use `.example` or `.test`. Banking identifiers contain `TEST` and are intentionally nonfunctional; no real routing/account number, credential or automatic-debit authorization is supplied.
- Ages, children, income and smoking disclosures are parser test fields; they are not tenant-screening criteria or reasons for different fees. No medical, nationality, government-ID or Social Security data is generated.
- Signature blocks are blank and labeled unsigned. The scenario agreement date is seven days before commencement, not a historical signature assertion. Corpus creation date is October 31, 2026.
- Annexure A records an approved pet or explicitly no approved pets. Five households have one pet; all recorded weights are below 50 pounds. A conditional $250 pet fee is distinguished from a current $0 pet fee for no-pet households. These terms are fictional, not legal-fee determinations.
- Annexure B covers smoking and vaping, annexure C trash/recycling, and annexure D a distinct unit-specific condition with separate acknowledgment lines. No minor signs an annexure. Emergency contacts are not guarantors.
- These packets do not automatically incorporate later policy-library revisions. Lease clauses and separately versioned property policies must remain distinguishable in retrieval.

## Suggested acceptance queries

| Query | Expected result |
| --- | --- |
| Maya's rent, household and approved pet? | $2,200/month; 3 people, 1 child; Miso, 11-pound cat. |
| James's smoking disclosure and pet charge? | Outdoor cigarette smoking; no approved pet; current pet fee $0. |
| Oliver's household and unit condition? | 4 people, 2 children; Unit 305 balcony-care annexure. |
| Ethan's parking condition? | Unit 3B guest permit subject to availability; no guaranteed space. |
| Isabella's lease duration? | December 16, 2025–December 15, 2026 inclusive; 12 calendar months. |
| Ava's payment on day 6 using sample terms? | $2,100 + $50 = $2,150; no claim about actual balance or legality. |
| Lucas's pre-existing damage? | Kitchen cabinet scratch and entry scuff, recorded as pre-existing. |
| Can tenant-1 retrieve tenant-2's bank token? | No; enforce backend tenant/lease isolation. |

The SHA-256 hashes in the manifest verify artifact identity, not legal correctness. Store sensitive-looking fields under normal access controls even though every value here is synthetic.

## Regeneration

From the repository root, use Node.js 22+:

```powershell
node scripts/build-synthetic-leases.mjs
node scripts/print-synthetic-leases.mjs
npm.cmd test
```

The first script reads the existing UI fixtures and deterministic enrichment profiles; it writes JSON, Markdown, HTML and the manifest. The second prints PDFs and adds PDF hashes/page counts to the manifest. Run both after changing fixtures. The layout deliberately preserves existing page citations.

PDF printing uses a local Chromium/Edge instance started with a separate browser profile and remote debugging on port 9224, as used by the existing integration-guide printing workflow. For example, on Windows:

```powershell
$leaseBrowser = "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe"
$leaseProfile = Join-Path $env:TEMP 'laga-lease-print-profile'
Start-Process -FilePath $leaseBrowser -WindowStyle Hidden -ArgumentList @('--headless=new', '--remote-debugging-port=9224', "--user-data-dir=$leaseProfile", 'about:blank')
```

If your browser is installed elsewhere, use its path. If a debugging browser already runs on 9224, reuse it. Set `LAGA_DOCUMENT_BROWSER` to another local debugging endpoint if needed. PDF generation requires a browser only during fixture regeneration; deploying or ingesting the checked-in PDFs does not require one.

# Phase 6C — activation attempt and current verification status

## Result: blocked before activation

**Live Pinecone integration was not activated or verified.**
Monica's reported successful ingestion is acknowledged, but no actual active
snapshot, approved binding or required credentials are available in this
workspace to verify that ingestion or query its correct resources.

The brief explicitly requires stopping activation if an artifact is missing.
No cloud calls, index changes, ingestion, fabricated snapshots, invented
approval records, mock fallback, or enable-flag changes were performed.
No commit, push, merge or background-agent execution was performed.
The normal application workflow was restarted for its preview/startup check.

This report describes the current state after synchronization. The earlier
`PHASE6C_READINESS.md` remains a historical pre-synchronization audit.

## 1. Source synchronization completed

Fetched `origin/feature/rag`; latest source remains:
`11044a36f41e86a2087d59a400abc9cef63c452c`.

- Root `documents.json` already exactly matches that source; no rewrite needed.
- Manifest SHA-256:
  `52e07f6d3264103136c61c3c5faf8b328ac1bd955cb074ddd4e4e3c2c299dafa`.
- Replaced only the referenced local PDF with the exact Git source bytes:
  `data/Free-North-Carolina-Standard-Lease-Agreement-Template.pdf`.
- Imported PDF: 26 pages, 337,692 bytes.
- Imported PDF SHA-256:
  `4a8c24f993152af5f4a61da328b3fcdf0932e2438114b20b343c5ef1d11dbf55`.
- Original 13-page template SHA-256:
  `86b47ae123220690d7476dfabc53e91e97177636ef818a51fc64cb54e2984573`.
- Preserved the original at
  `artifacts/lease_rag_local/activation-review/original-lease-86b47ae123220690d7476dfabc53e91e97177636ef818a51fc64cb54e2984573.pdf`.

The ignored review directory also contains `source-sync-receipt.json` and
tracked-file verification hashes. These describe **local file synchronization
only**, not Pinecone ingestion, an active snapshot, or production approval.

## 2. PDF and identity verification completed

The imported bytes match the fetched Git object exactly. Extracted PDF text
contains the approved tenant, tenant ID, lease ID, document ID, property ID,
term dates, and explicit synthetic/unsigned notices.

All 12 appended pages (combined pages 15–26) match the existing UI Maya packet
by extracted page text. No other primary tenant name from the bootstrap corpus
was found in this PDF; this is an offline content check, not a live isolation
result. Household members and the landlord are part of the declared source.

Read-only checks of the existing SQLite database reconfirmed:

```text
org-alder-demo
  tenant-1 / Maya Chen
    lease-1 / property-1
      documents: [lease-document-1]
```

The manifest's `lease_id` and `document_id` remain distinct. Status remains
`synthetic_unsigned`; it was not rewritten to `signed`.
Transferred fields and template boilerplate caveats are preserved; no
contractual precedence or legal enforceability was inferred.

## 3. Exact activation blockers

| Requirement | Actual workspace status |
| --- | --- |
| Approved operator bindings | Default `rag_bindings.json` absent |
| Complete manifest identity fields | `tenant_id`, `organization_id`, `backend_document_id` absent |
| Active ingestion snapshot | Default `artifacts/lease_rag_local/active.json` absent |
| Dense/sparse index names | No configured workspace values returned |
| Correct namespace | No configured value or actual snapshot available |
| Ingested embedding profile | Not supplied/verified against a snapshot or indexes |
| `PINECONE_API_KEY` | Absent from development/shared Replit Secret metadata |
| Selected embedding provider key | Both `NEBIUS_API_KEY` and `FIREWORKS_API_KEY` absent |
| Local settings fallback | `.env` absent; no custom settings-file/path overrides returned |
| Production eligibility | Current signed-only preflight rejects `synthetic_unsigned` |
| Latest upstream record compatibility | Existing adapter/module versions are not compatible with all new formats |

Secret checks used `viewEnvVars(type="secret")`: existence only, never values.
No credentials were requested in chat, written to files, or configured.
Future sensitive credentials must be provisioned through Replit Secrets, not
through the manifest, binding JSON, attachment, source code, or report.
Index existence and ingestion completion are **unknown**, not declared absent.
Only the required local/configuration inputs are confirmed missing.

### Existing factory's exact approval requirements

`src/laga/rag_mapping.py::verify_scope()` first checks authoritative backend
ownership, then requires a real snapshot with:

- Integer schema version 1.
- Exact configured embedding profile and dense/sparse index names.
- Namespace `leases-v1-<24 lowercase hexadecimal characters>`.
- Positive chunk count and a document ownership registry.

It requires a strict operator binding with schema version, exact snapshot and
manifest byte hashes, and document rows containing organization ID, tenant ID,
tenant name, lease ID, backend document ID, Pinecone document ID and PDF SHA-256.
Every associated backend document must be covered uniquely.

The manifest must explicitly match those ownership fields and declare tenant
access, lease type, and **signed** status. The PDF hash and snapshot ownership
must match. Source chunks are independently rebuilt from the approved PDF.

Only then does `ProductionRetrieverFactory` initialize clients and validate
ready, existing dense/sparse indexes, dimensions/metrics and namespace counts.
No index creation/upsert is part of this factory.

No synthetic approval binding or snapshot was generated to satisfy these checks.
Do not relabel an unsigned fixture to bypass them. If synthetic live demos are
required, their eligibility needs an explicit separately reviewed policy.

### Compatibility blockers preserved rather than bypassed

The fetched RAG branch includes newer corpus/record-ID and banner-stripping
behavior. Existing local Phase 6B code and tests were preserved:

- New ingestion uses `record_id` with a corpus-hash suffix; the current local
  `restore_document()` checks vector ID against the original `chunk_id`.
- New retrieval filters by `corpus_id`.
- New configuration supports a namespace override; the current adapter enforces
  its pinned namespace format and exact total vector count.
- New chunking strips configured repeated banners; the current chunker does not.

An actual snapshot and record sample are needed to verify which format Monica
ingested. Do not assume that an updated PDF implies an adapter-compatible corpus.

## 4. Requested live retrieval and demo results

**No live sources were retrieved.** The read-only lease-end-date query was not
executed because the prerequisites failed. Therefore it has no reported
Pinecone citations, page numbers or cross-tenant verification result.

None of the five signed-in live demo scenarios was executed or certified:

1. Lease expiration.
2. Pet permission.
3. Late-payment terms.
4. Applicable late fee.
5. Multi-part expiration/security-deposit question.

The fee scenarios must still ask for missing payment facts before arithmetic;
reading a contractual fee alone does not establish eligibility or payment dates.
Existing passing fake-client tests are not substituted for these live scenarios.

## 5. Actual regression results

| Check | Result |
| --- | --- |
| Full Python suite | **211 passed, 1 failed** |
| Additional subtests | **57 passed** |
| Frontend tests | **42 passed** |
| Frontend production build | **Successful** |
| OpenAPI component meta-validation | **26 schemas passed** |
| Cross-tenant authorization/filter regressions | Passed within Python suite; isolated/fake-client tests |
| Live Pinecone tenant isolation | Not executed |
| Preview/startup | Existing workflow restarted and started cleanly; login page rendered |

No tests skipped. One third-party Starlette/AnyIO deprecation warning.
Signed-in UI, actual Pinecone citations and displayed live fee calculations were
not verified. The browser check did not bypass authentication.

### The one Python regression

```text
tests/test_local_rag.py::LocalRagTests::
test_real_pdfs_preserve_citations_blank_pet_fields_and_unique_ownership

Expected pet section page_numbers: [2]
Actual with imported PDF and preserved chunker: [2, 3]
```

This original test assumes the old blank-template layout. The newly approved
PDF changes the evidence spans. Neither the test assertion nor the retrieval/
chunking implementation was changed to conceal the mismatch. The full suite is
**not green**, and this compatibility issue must be reviewed before readiness
can be claimed.

## 6. Remaining work and readiness

**Not ready for deployment with live LAGA retrieval.** File synchronization is
complete, but activation is blocked and one regression remains.

Required next inputs/approvals:

1. Monica's actual active snapshot/ingestion receipt, dense and sparse index
   names, namespace, embedding profile and record/corpus identity format.
2. Complete approved ownership bindings and manifest fields pinned to the exact
   imported PDF, actual manifest and actual snapshot.
3. Required Pinecone and selected provider credentials in Replit Secrets.
4. Reviewed unsigned-demo eligibility decision, without weakening tenant
   authorization or pretending the fixture is an executed agreement.
5. Reviewed corpus/chunking compatibility and resolution of the stale test-layout
   assumption, preserving citation fidelity.
6. Only after prerequisites pass: read-only live retrieval, two-tenant isolation,
   source comparison and the five authenticated UI-to-Pinecone scenarios.

The confirmed source import did not require re-ingestion, index modification,
auth/SQLite changes, new packages or modification of existing agent/backend/
frontend/RAG code or tests.

## Changed files

- Updated the requested tracked RAG PDF only.
- Added this report.
- Preserved the old PDF and a source-sync receipt under the existing ignored
  RAG artifact directory.
- Root ignored manifest remained byte-identical to upstream and unchanged.

All other previously tracked files are unchanged. No changes were staged.

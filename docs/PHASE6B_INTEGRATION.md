# Phase 6B — production retrieval adapter

## Status

The opt-in production adapter is implemented and regression-tested. It is
**disabled by default and has not been verified against live Pinecone**.
Neither approved bindings nor an active snapshot exists at the default paths
in this workspace. Passing mocked tests does not approve real tenant mappings.

No credentials were requested, configured, read through agent tools, or logged.
No Pinecone indexes were created, changed, populated, or deleted. No commits,
pushes, merges, or background-agent execution were performed.

## Verified interfaces and unchanged components

```python
factory(tenant_id, tenant_name, lease_id) -> retriever
retriever.invoke(query) -> list[LangChain Document]
```

`ProductionRetrieverFactory` wraps the actual, unchanged
`lease_rag.retrieval.TenantHybridRetriever`. It does not replace hybrid search,
weighted reciprocal-rank fusion, dense/sparse embeddings, `authorized_scope()`,
or storage identity checks.

`BackendAPI.post_assistant_messages()` retains its signature, existing
principal/permission/lease authorization, and the existing graph call.
The backend constructor selects production retrieval only when explicitly
requested. An explicitly injected test factory continues to use the old seam.

`AssistantIntegration` adds a production-only preflight after authorization
and thread checks, before graph execution. Both configured document IDs and
provider failures remain server-owned; browser questions cannot set them.
Unexpected production retrieval failures are not converted into successful
partial answers by the graph's bounded retry: the per-request failure state
is checked again before returning the Answer DTO.

## Identity and approval boundary

Every request re-reads the authoritative account and lease through the existing
backend helpers. Before any cloud client initialization, it verifies:

1. Tenant ID, authoritative profile name, internal organization ID, lease ID,
   lease ownership, and the complete associated backend document set.
2. The original snapshot's schema, embedding profile, index names, namespace,
   and positive chunk count.
3. Exact SHA-256 pins of the snapshot and ingestion manifest.
4. Explicit, unique backend-to-Pinecone document bindings.
5. Manifest tenant/organization/lease/backend-document identities, normalized
   tenant name, and membership in the snapshot's owned-document registry.
6. PDF byte hashes and operator-declared `document_type=lease`,
   `document_status=signed`. Templates/unknown/unsigned records fail preflight.
7. Canonical chunks rebuilt read-only with Monica's unchanged chunker from
   the verified local PDFs.

Names alone, matching filenames, parsed PDF names, and available credentials
never grant ownership. The original demo template cannot be silently assigned
to a SQLite tenant.

Bindings must cover every document associated with the selected backend lease.
Pinecone document IDs must be unique across the pinned binding registry.
Different backend and Pinecone IDs are supported only through this verified
mapping; arbitrary retrievers do not acquire a broader document allowlist.

## Operator-maintained input formats

The ingestion manifest retains Monica's original format. Each production lease
record additionally needs these explicit trusted fields:

```json
{
  "path": "<relative signed PDF path inside the configured data directory>",
  "document_id": "<Pinecone document ID>",
  "tenant_name": "<authoritative account name>",
  "tenant_id": "<SQLite user ID>",
  "organization_id": "<internal SQLite organization ID>",
  "lease_id": "<SQLite lease ID>",
  "backend_document_id": "<one exact ID from Lease.documents>",
  "access": "tenant",
  "document_type": "lease",
  "document_status": "signed",
  "document_title": "<actual document title>"
}
```

Default private binding file: `rag_bindings.json`.
The following is a **schema illustration with invalid placeholders**, not an
approved mapping or an instruction to enable retrieval:

```json
{
  "schema_version": 1,
  "snapshot_sha256": "<SHA-256 of exact approved active.json bytes>",
  "manifest_sha256": "<SHA-256 of exact approved documents.json bytes>",
  "documents": [
    {
      "organization_id": "<internal SQLite organization ID>",
      "tenant_id": "<SQLite user ID>",
      "tenant_name": "<authoritative account name>",
      "lease_id": "<SQLite lease ID>",
      "backend_document_id": "<one exact ID from Lease.documents>",
      "pinecone_document_id": "<exact manifest document_id>",
      "document_sha256": "<SHA-256 of the actual signed PDF bytes>"
    }
  ]
}
```

Operators must review the ownership assignment before creating these pins.
Editing the manifest or replacing the snapshot requires renewed review and
matching pins, not automatic approval. Keep real PDFs and identity bindings
private and outside frontend/static build output. The default binding file,
operator manifest, generated RAG artifacts, and non-public data stay ignored.
A dedicated private corpus directory avoids mixing public fixtures with signed
tenant documents.

## Configuration and environment precedence

No new package dependencies or competing manifests were added.

The new adapter configuration reads only its allowlisted settings. Values in
`os.environ` override local dotenv values, including explicit empty values
which fail required-setting checks rather than falling back to stale keys.
Dotenv interpolation is disabled. Existing `lease_rag.config.Settings.load()`
and the original CLI behavior remain unchanged.

| Setting | Meaning/default |
| --- | --- |
| `LAGA_RAG_ENABLED` | Explicit `true`/`1` requests production retrieval; default disabled |
| `LAGA_RAG_ENV_FILE` | Optional local dotenv path; otherwise project `.env` |
| `LAGA_RAG_BINDINGS_FILE` | `rag_bindings.json` |
| `LAGA_RAG_MANIFEST_FILE` | `documents.json` |
| `LAGA_RAG_DATA_DIR` | `data` |
| `LAGA_RAG_SNAPSHOT_FILE` | `artifacts/lease_rag_local/active.json` |
| `EMBEDDING_PROVIDER` | Monica's `nebius` default or `fireworks` |
| `PINECONE_INDEX_NAME` | Required existing dense index |
| `PINECONE_SPARSE_INDEX_NAME` | Existing sparse index; original dense-name + `-sparse` default |
| `PINECONE_API_KEY` | Required credential |
| `NEBIUS_API_KEY` / `FIREWORKS_API_KEY` | Credential for the selected embedding provider |

The backend uses existing extractive graph generation and deterministic
arithmetic; it does not initialize a chat LLM or require a generation key.
Secrets are not included in configuration representations or public errors.

Only after local scope verification does the adapter initialize clients and
perform read-only checks of existing resources:

- Distinct valid lowercase Pinecone index names.
- Ready dense cosine index with the configured 4096 dimensions.
- Ready sparse dotproduct index.
- Exact pinned `leases-v1-<24 lowercase hex characters>` namespace.
- Namespace vector count equal to the snapshot's total chunk count in both
  indexes. Missing/eventually inconsistent resources fail closed.

There is no call to `prepare_index`, `create_index`, ingestion, or upsert.
The original ingestion CLI remains unchanged and retains its cloud-write
behavior; running it requires a separately approved ingestion/setup step.

## Evidence and citation fidelity

The snapshot passed to Monica's retriever is narrowed to the selected lease's
verified Pinecone document IDs. `authorized_scope()` still executes and the
same tenant/document filter applies to both searches. Shared/statute records
are absent from this scope and cannot become signed lease evidence.

Returned text and canonical provenance metadata must match chunks reconstructed
from the verified PDF. This catches corrupted bodies even if stored tenant,
document and hash labels look correct.

Original `document_id`, `chunk_id`, `page_numbers`, `section_id`, nullable
`clause_id`, `citation_label`, `source_text`, source spans and context remain in
the evidence metadata. Verified backend tenant/organization/lease identity and
the associated backend document ID are enriched without replacing Pinecone's
original document ID. Conflicting identity metadata is rejected.

The agent receives the literal source body rather than embedding breadcrumbs/
parent context. No scalar page or clause ID is fabricated. The existing closed
public Citation DTO remains unchanged: it exposes its existing source ID,
document ID, title, section, one actual source page, and quote. Full page lists,
chunk identity and span metadata remain in the internal evidence documents.
An actual section ID is used for the UI label when the source clause ID is null.

The original fee calculator, its result schema and Decimal dollar-to-cent
adapter remain unchanged. Compliance always remains `unavailable`.

## Safe failure codes

All integration errors use the existing HTTP 503 error envelope:

- `RAG_UNAVAILABLE`: disabled/unconfigured retrieval, absent snapshot,
  client initialization or provider failure.
- `RAG_CONFIGURATION_ERROR`: invalid settings, profile, indexes or namespace.
- `RAG_MAPPING_INVALID`: missing/unapproved/inconsistent bindings, ownership,
  manifest, PDF or signed-document provenance.
- `RAG_EVIDENCE_INVALID`: foreign/shared, corrupted or noncanonical evidence.

Existing authentication, CSRF, role, lease and thread errors retain their
existing behavior/status codes. Provider exception details never enter errors.

## Actual validation

- Full Python suite: **203 passed**, plus **57 subtests passed**.
  Includes the original 150 tests and 53 new adapter/security cases.
- Monica's original RAG suite, separately: **11 passed**.
- Frontend: **42 passed**.
- Frontend production build: successful.
- OpenAPI: **26 component schemas** passed JSON Schema meta-validation.
  API/adapter success and error responses also passed the existing contract
  validation throughout the Python and frontend suites.
- **Zero failures or skips**; one third-party Starlette/AnyIO deprecation warning.
- Development workflow restarted once after code changes and started cleanly.
  The login page was screenshot-verified. Signed-in UI was not browser-tested;
  authenticated behavior was exercised through HTTP integration tests.
- All **75 protected files** are unchanged, including existing tests, agent,
  calculator, Monica's modules, frontend, OpenAPI, dependency files and `.replit`.
- AST comparison found only the backend constructor changed; authentication,
  SQLite methods/schema and `post_assistant_messages()` are unchanged.

Test cases use fake Pinecone/embedding clients, synthetic PDFs, and temporary
approved inputs. They execute the actual hybrid retrieval and graph/calculator
code, but are **not live service, real-key or real-tenant verification**.

## Changed files

New:
- `src/laga/rag_configuration.py`
- `src/laga/rag_mapping.py`
- `src/laga/rag_integration.py`
- `tests/test_production_rag.py`
- `docs/PHASE6B_INTEGRATION.md`
- `.agents/memory/verified-rag-activation.md`

Modified:
- `src/laga/backend_api.py`: constructor integration selection/docstring only.
- `src/laga/assistant_integration.py`: verified production preflight, scoped
  document-ID translation, sticky failure check and real section-ID label.
- `.gitignore`: ignore the default private binding file.
- `.agents/memory/MEMORY.md`: pointer to the activation boundary decision.

## Is it safe to enable?

The implementation is safe-by-default and suitable for a **controlled activation
after real inputs are independently approved**. It is **not approved for live
use with the current demo corpus** and remains disabled here.

Before activation, supply the actual signed PDFs and authoritative mapping,
verified original ingestion manifest/snapshot and pins, correctly configured
existing indexes/namespaces, approved workspace credentials, and matching
embedding configuration. Then perform a separately approved live read-only
smoke test including two-tenant isolation and citation verification.

Local canonical chunk verification adds PDF parsing work per request and
requires the approved source PDFs and matching extraction/chunker versions to
be present on the backend. Root-package portable distribution and process-local
thread history limitations from earlier phases are not changed by this work.

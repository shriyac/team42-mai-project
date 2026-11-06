# Phase 6A — safe import of Monica's RAG implementation

## Git safety and provenance

- Work remained on `main`; no checkout, commit, push, or branch merge.
- Fetched and verified `origin/feature/rag`.
- Source commit: `aba96837e859569f5c0f14e4b7bb81985396cb55`.
- Created local safety branch
  `safety/phase6a-before-rag-import-20261104-193801` at the original HEAD
  before importing or modifying files.
- The current branch remains nine commits ahead of its local `origin/main`
  reference. Import/configuration changes are unstaged.

## Imported files

All thirteen files are byte-identical to their source branch versions:

```text
lease_rag/__init__.py
lease_rag/chunking.py
lease_rag/config.py
lease_rag/embeddings.py
lease_rag/manifest.py
lease_rag/retrieval.py
lease_rag/storage.py
ask_lease.py
ingest_leases.py
documents.example.json
tests/test_local_rag.py
data/Free-North-Carolina-Standard-Lease-Agreement-Template.pdf
data/NC_general_statutes_Chapter_42.pdf
```

The two PDFs are the public fixtures required by the upstream unit tests.
No existing files were overwritten by the import.

## Conflicts and preservation

Source `README.md`, `.gitattributes`, and `.gitignore` differ from local files.
Their differences were reviewed; none was copied over the local version.
The upstream `.env.example` and `requirements.txt` were not imported.
The latter was reviewed as dependency input, not added as a competing manifest.

The local `.gitignore` received a narrow additive change: permit only the two
public sample PDFs while keeping all other `data/` contents ignored; also
ignore `documents.json` and generated `artifacts/lease_rag_local/` snapshots/
caches. Ignore checks confirmed local database files, bootstrap credentials,
private PDFs, `.env`, and generated RAG artifacts remain excluded.

SHA-256 checks verified that all **72 pre-existing protected files** under
`agent/`, `laga_agent/`, `tools/`, `src/laga/`, `frontend/`, `contracts/`, existing
`tests/`, plus `.replit`, are unchanged.

## Dependency reconciliation

The upstream requirements target LangChain 0.3, which conflicts with the
existing LangGraph 1.2.19 requirement `langchain-core>=1.4.7,<2`.
The agent was not downgraded and Monica's algorithms were not modified.
Her unchanged tests instead verified the compatible LangChain 1.x packages.

`pyproject.toml` remains the canonical manifest, with its existing settings,
LangGraph dependency, API/test extras, scripts, and build configuration retained.
Seven RAG requirements were added to the main dependency list so the unchanged
preview and full-suite commands continue to work without new extra flags.
`uv.lock` was updated using the existing uv package manager.

| Package | Upstream requirement | Combined requirement | Installed |
| --- | --- | --- | --- |
| pypdf | `>=6,<7` | `>=6,<7` | 6.21.4 |
| langchain-core | `>=0.3.86,<0.4` | `>=1.4.7,<2` | 1.7.4 |
| langchain-text-splitters | `>=0.3.11,<0.4` | `>=1,<2` | 1.1.3 |
| langchain-openai | `>=0.3.35,<0.4` | `>=1,<2` | 1.7.3 |
| pinecone | `>=7.3,<8` | unchanged | 7.3.0 |
| openai | `>=1.104,<3` | unchanged | 2.54.0 |
| python-dotenv | `>=1,<2` | unchanged | 1.2.4 |

LangGraph remains **1.2.19** and the existing langchain-core remains **1.7.4**.
pypdf was already in the test extra; it is now also a runtime requirement for
the imported PDF ingestion code. No unrelated direct packages were added.
The resolver also selected packaging 24.2 in place of 26.3; other transitive
additions are recorded in the lockfile.

## Actual validation

```sh
uv sync --extra api --extra test
uv run --extra api --extra test python -m pytest -q tests/test_local_rag.py
uv run --extra api --extra test python -m pytest -q
npm test
uv run --extra api --extra test python ask_lease.py --help
uv run --extra api --extra test python ingest_leases.py --help
```

- `import lease_rag`: successful.
- `lease_rag.retrieval.TenantHybridRetriever`: available.
- Imported RAG unit tests, isolated: **11 passed**.
- Full Python suite: **150 passed**, including all **139 existing regressions**
  and all **11 imported tests**, plus **57 subtests passed**.
- Frontend: **42 passed**, zero failures.
- Both CLI help/import checks passed without initializing service clients.
- All thirteen imported files matched the upstream Git blobs.
- All 72 protected originals matched their pre-import hashes.
- Existing development workflow restarted once and serves successfully on
  ports 5000/8001. Login page screenshot showed no browser errors; signed-in UI
  was not browser-tested.
- One third-party Starlette/AnyIO deprecation warning in the full Python suite.
- uv retained the existing non-packaged source-checkout behavior; its warning
  about skipped console entry points was not addressed by changing packaging.

RAG tests use fake clients/indexes and temporary settings/snapshots. No live
Pinecone, embedding, or generation requests were made. The default active
snapshot does not exist. No real credentials were read, requested, or added.

## Remaining integration blockers — not implemented in Phase 6A

1. **Authoritative identity/document mapping.** The upstream manifest/snapshot
   uses normalized `tenant_name` and `document_id`. It does not establish
   SQLite account or organization membership. Example IDs/names do not match
   the backend's lease-document registry. Lease metadata `lease_id` is optional
   in the chunker and absent from the example manifest. The existing agent
   requires the correct lease ID. Build a trusted mapping before retrieval;
   never derive permissions from question text or tenant name alone.
2. **Factory wiring.** Adapt `TenantHybridRetriever` construction to the existing
   `(tenant_id, tenant_name, lease_id) -> retriever.invoke(query)` interface.
   Select `document_ids` from authorized SQLite leases, retain the backend
   allowlist, and preserve scope filters on both dense and sparse searches.
   Backend `assistant_retriever_factory` remains `None`, so default authorized
   chat still returns `503 RAG_UNAVAILABLE`.
3. **Settings and credentials.** `Settings.load()` explicitly reads a local
   `.env` file and intentionally ignores shell secrets. A future backend
   settings bridge must deliberately use approved workspace configuration.
   Required retrieval credentials are `PINECONE_API_KEY` and the selected
   `NEBIUS_API_KEY` or `FIREWORKS_API_KEY`; index names/provider/profile must
   also be configured. Generation has separate model/key settings and is not
   needed simply to connect retrieval. No keys were provisioned in this phase.
4. **Verified ingestion snapshot.** Querying needs a profile-matching active
   snapshot, owned document registry, dense 4096-dimensional cosine index, and
   sparse dotproduct index. No indexes or snapshots were created. The example
   lease is an unfilled template, not a substitute for a tenant's signed terms.
5. **Evidence and answer compatibility.** Preserve original source spans,
   section/clause identities and page-number lists when adapting citations.
   Monica's retriever also permits shared statute evidence; the current agent
   excludes shared/statute chunks from tenant lease evidence. Do not loosen
   that boundary or fabricate compliance approval. Her optional generated
   answers are not automatically wired into the graph's strict extractive
   grounding validation.
6. **Portable distribution.** The existing package discovery still targets
   `src`; standalone packaging of root-level `agent`, `tools`, and now
   `lease_rag` remains separate work. No packaging or thread-history rewrite
   was attempted.

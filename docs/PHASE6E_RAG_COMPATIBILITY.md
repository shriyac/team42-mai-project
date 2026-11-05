# Phase 6E — RAG compatibility reconciliation

## Outcome and limits

Fetched `origin/feature/rag` at
`11044a36f41e86a2087d59a400abc9cef63c452c`. The workspace started on `main`
with a clean working tree, fourteen commits ahead of `origin/main`.
No commit, push, merge, background task, cloud ingestion, Pinecone write,
or live activation was performed.

The local production bridge now supports the upstream corpus format. This is
**code compatibility, not verification of the actual indexed corpus**: its
real ingestion snapshot and approved bindings are still unavailable.
All cloud interactions in tests used fake clients and temporary fixture
artifacts. No operational snapshot, binding approval, or PDF hash was fabricated.

## Exact upstream comparison and source reconciliation

The following four modules now match the fetched upstream bytes exactly:

| File | Relevant upstream changes |
| --- | --- |
| `lease_rag/config.py` | `Settings.namespace` reads `PINECONE_NAMESPACE`. The embedding profile remains unchanged. |
| `lease_rag/storage.py` | `ingest_documents` calculates the corpus fingerprint from profile and sorted pre-upload chunk metadata. Vector IDs become `chunk_id + ":" + corpus_id[:24]`. Full `corpus_id` and `record_id` appear in flat filterable metadata and nested `evidence_json`. `restore_document` checks both identities and the vector ID. |
| `lease_rag/retrieval.py` | `load_snapshot` checks an explicit namespace override. `authorized_scope` adds an active-corpus equality filter. `TenantHybridRetriever` rejects inactive-corpus hits and changes its default dense weight from 0.5 to 0.7. Upstream generation adds strict inline-citation normalization/validation and one correction attempt using the same evidence. |
| `lease_rag/chunking.py` | `extract_document` retains configured warnings and removes exact configured `repeated_header_footer_lines` before building source text and offsets. Canonical source spans, page coverage, and chunk IDs can therefore change even when PDF bytes do not. |

`ingest_leases.py` has no differences and was not changed.
The ignored operational `documents.json` already matches upstream exactly and
was not changed. It contains the Maya synthetic-unsigned fixture and a shared
NC Chapter 42 reference. Existing PDF bytes, manifest, and pending binding
candidate were preserved.

The snapshot remains `schema_version: 1`, but now includes a full `corpus_id`.
Its namespace is either the explicit override or `leases-v1-<first 24 corpus
hex characters>`. Chunk IDs remain citation identities; vector record IDs are
separate, corpus-versioned storage identities. Reused namespaces may contain
multiple corpus versions, so their total vector count is not an active-corpus
completion proof.

No upstream retrieval or ingestion algorithm was locally edited. Ingestion
code was imported, not executed against Pinecone. Existing tests exercising
ingestion use in-memory fake indexes only.

## Production bridge changes

### `src/laga/rag_configuration.py`

- Added `PINECONE_NAMESPACE` to the existing allowlist, retaining environment
  precedence and secret-safe representations.
- Validate configured namespaces for size/control characters.
- No environment settings or secrets were created or changed.

### `src/laga/rag_mapping.py`

- `verify_scope` accepts corpus-format snapshots and explicitly configured
  namespaces, while retaining strict legacy namespace validation.
- New `verify_corpus` read-only verification reproduces upstream's pre-upload
  fingerprint using the pinned manifest/PDFs, canonical chunks, profile, and
  `pinecone_metadata`. It checks the complete document registry, chunk count,
  unique IDs, corpus digest, and generated namespace when no override exists.
- This computed digest is a comparison against an independently supplied
  pinned snapshot, not a new snapshot or operator approval.
- Snapshot/manifest hashes are checked again before returning the scope.
- Existing SQLite authorization, explicit approved bindings, source hashes,
  complete backend document coverage, source eligibility, synthetic-demo
  restrictions, and narrowing to the authorized lease remain mandatory.

### `src/laga/rag_integration.py`

- `_indexes` receives the verified scope. Legacy namespaces still require exact
  total counts. Corpus namespaces may include inactive versions, so totals must
  be at least the pinned corpus count.
- The count check is supplemented, not simply relaxed: before any search, both
  indexes must return **every authorized canonical chunk's exact corpus-suffixed
  record ID** via read-only fetches. Missing records fail closed, even with a high
  namespace count. Fetched identities, text, and provenance must validate.
- This check fetches only the authorized lease's records, not other tenants'
  evidence or shared statutes. It establishes availability for the authorized
  scope, not remote completeness of every other tenant's corpus.
- `normalize_document` requires the pinned corpus and exact record suffix,
  retaining all canonical text, PDF digest, source-span/page, ownership, status,
  and backend identity checks. Corpus records cannot be paired with an unpinned
  legacy snapshot.
- Both dense and sparse queries use upstream corpus filters plus the existing
  narrowed tenant/document registry. Unsupported or inconsistent evidence is
  withheld; no mock fallback was introduced.
- LangGraph, fee arithmetic, public DTO adapters/citation validation, backend,
  authentication, SQLite, frontend, and contracts were not modified.

## Dependencies

No dependency or lockfile changes were required. Preserve the reconciled
LangChain 1.x / LangGraph family in `pyproject.toml`; do not install the
upstream legacy LangChain 0.3 requirements as a competing manifest.

## Tests and actual results

Commands:

```sh
uv run --extra api --extra test python -m pytest -q
uv run --extra api --extra test python -m pytest -q \
  tests/test_local_rag.py tests/test_rag_corpus_compatibility.py
uv run --extra api --extra test python -m pytest -q \
  tests/test_production_rag.py tests/test_synthetic_demo.py \
  tests/test_rag_corpus_compatibility.py \
  -k 'tenant or scope or ownership or mapping or demo_never'
npm test
npm run build
```

| Validation | Result |
| --- | --- |
| Full Python regression suite | **257 passed; 57 subtests passed** |
| Imported RAG + new compatibility tests | **34 passed** (15 imported/local RAG, 19 new compatibility cases) |
| Focused tenant/scope/ownership/approval isolation | **23 passed; 71 deselected** |
| Frontend | **42 passed** |
| Frontend production build | **Successful** |

Python runs have one pre-existing third-party Starlette/AnyIO deprecation
warning. No final test failures.

`tests/test_local_rag.py` retains existing tests, adds four upstream cases for
citation validation and reused-namespace ingestion, and makes the existing
equal-weight fusion test explicitly select 0.5 instead of relying on an old
default. The new default 0.7 is separately asserted. The example-manifest pet
page expectations remain unchanged: unlike the operational manifest, that
fixture does not configure banner removal.

New `tests/test_rag_corpus_compatibility.py` covers exact record fetches in both
indexes, generated/overridden namespaces, mixed versions, missing/corrupt records,
stale-corpus results, independent hash/registry/count checks, tenant isolation,
banner-stripped spans, and synthetic-demo disclosure and off-switch behavior
through the corpus-format bridge.

Initial verification issues resolved:

- Direct `pytest` did not put the unpackaged repository on the import path;
  use the project's `python -m pytest` invocation. A standalone diagnostic
  likewise needed `src` on its import path; no package configuration was changed.
- One new forged-record test changed only the dense result. Upstream correctly
  withheld inconsistent dense/sparse evidence as `RAG_UNAVAILABLE`, before the
  bridge's record validator. The test now changes both fake hits coherently to
  exercise the intended exact-record rejection (`RAG_EVIDENCE_INVALID`).
  Runtime checks were not relaxed to make the test pass.

## Activation check and remaining blockers

Observed at completion:

- `LAGA_RAG_ENABLED`: not enabled; `activation_requested()` is false.
- Synthetic-demo activation flag: not enabled.
- `artifacts/lease_rag_local/active.json`: **absent**.
- Approved `rag_bindings.json`: **absent**.
- `rag_bindings.pending.json`: present, pending only, not approved or executable.
- `documents.json`: present and upstream-exact, but missing the required
  `organization_id`, `tenant_id`, and `backend_document_id` on the lease record.
- Replit secret existence checks in development/shared and production/shared:
  `PINECONE_API_KEY`, `NEBIUS_API_KEY`, and `FIREWORKS_API_KEY` are all **absent**.
  Only existence metadata was inspected; no credential values were displayed.
- No explicit index/namespace/activation settings were returned by the
  development/shared environment metadata check.

Remaining requirements:

1. Obtain the **actual successful ingestion snapshot** from Monica, including
   corpus ID, profile, both index names, namespace, registry, and chunk count.
2. Obtain independently reviewed ownership bindings pinned to that actual
   snapshot and the final authoritative manifest, and verify required ownership
   fields without assuming names or filenames prove identity.
3. Verify that the actual indexed metadata/source chunks match the reviewed
   PDFs and upstream banner-stripped extraction. If they differ, stop and report
   the mismatch; do not silently accept stale evidence or re-ingest.
4. Supply credentials for Pinecone and the selected embedding provider through
   Secrets, plus the reviewed nonsecret resource settings.
5. Perform separately authorized, read-only live checks. Fixture tests do not
   establish live service compatibility, approve bindings, or justify activation.

No live indexed corpus could be verified in this phase; live retrieval remains
disabled. No re-ingestion was attempted.

## Changed file list

- `lease_rag/config.py`
- `lease_rag/storage.py`
- `lease_rag/retrieval.py`
- `lease_rag/chunking.py`
- `src/laga/rag_configuration.py`
- `src/laga/rag_mapping.py`
- `src/laga/rag_integration.py`
- `tests/test_local_rag.py`
- `tests/test_rag_corpus_compatibility.py` (new)
- `docs/PHASE6E_RAG_COMPATIBILITY.md` (new)
- `.agents/memory/verified-rag-activation.md` (durable approval/compatibility policy)

# Phase 8A — Monica corpus target preparation

## Outcome: prepared, not activated

Local ownership, document identity, PDF hash and the supplied sample chunk
match. The current production adapter now supports an optional expected-corpus
pin in addition to its existing snapshot/fingerprint checks.

No Pinecone, embedding or LLM requests were made. No ingestion, approved
snapshot generation, binding approval or record writes were performed.

## Operator-supplied target

The development environment now records these non-secret values:

| Setting | Value |
| --- | --- |
| `PINECONE_INDEX_NAME` | `laga-rag` |
| `PINECONE_SPARSE_INDEX_NAME` | `laga-rag-sparse` |
| `PINECONE_CLOUD` | `aws` |
| `PINECONE_REGION` | `us-east-1` |
| `PINECONE_NAMESPACE` | `laga-hydrid` |
| `LAGA_RAG_EXPECTED_CORPUS_ID` | `74176289f06d1ecbcb70b901b1fb4fb1f6194194623a06502151ce431f005fc0` |
| `LAGA_RAG_ENABLED` | `false` |
| `LAGA_RAG_SYNTHETIC_DEMO_ENABLED` | `false` |

The namespace is intentionally preserved exactly; it was not changed to
`laga-hybrid`. These are operator-supplied targets, not independently verified
live resource properties. Production-environment settings were not changed.

Cloud and region are retained as settings; they have not been checked against
live index descriptions. Retrieval addresses indexes through their described
hosts, not by treating region settings as a substitute for resource inspection.

## Satisfied local prerequisites

- Read-only SQLite inspection confirms `tenant-1` owns `lease-1` at
  `property-1` in the active fictional database.
- SQLite lists `lease-document-1` for this lease.
- The actual local manifest maps `lease-1` to `lease-document-1` with tenant
  name `maya chen`, property `property-1`, and status `synthetic_unsigned`.
- The actual local PDF hashes to
  `4a8c24f993152af5f4a61da328b3fcdf0932e2438114b20b343c5ef1d11dbf55`.
- The supplied corpus ID is 64 lowercase hexadecimal characters.
- Current canonical PDF extraction contains
  `chunk-00ca13e73b6255ca84bb9b32` with section `23`, clause `23(m)`,
  page numbers `[6]`, and document `lease-document-1`.
- Pending candidate ownership IDs agree with the SQLite organization/tenant/
  document registry. That agreement is not binding approval.

No clause text, credentials or tenant database contents were printed.

## Sample metadata compatibility is not complete evidence

The supplied chunk fields have compatible types and match local canonical
extraction. Current upstream storage uses an immutable record identity of
`chunk_id + ":" + corpus_id[:24]`.

Filterable Pinecone metadata includes chunk/document identity, tenant name,
access, source filename, document type/status, text, corpus identity,
record identity and `evidence_json`. Clause/page/source-span provenance is
preserved inside the evidence JSON; the supplied partial sample is not a
replacement for that evidence.

The production adapter still checks both dense/sparse records, ownership,
allowlists, PDF hashes, canonical text/provenance and the complete corpus
fingerprint. Local sample agreement does not establish that live records or
all other corpus documents match.

## Exact missing inputs

### Actual ingestion snapshot

Expected default path: `artifacts/lease_rag_local/active.json`
(or an explicitly provided `LAGA_RAG_SNAPSHOT_FILE`).

The file is absent. The current upstream snapshot schema requires:

| Field | Required actual value |
| --- | --- |
| `schema_version` | Integer `1` |
| `namespace` | Exact actual namespace, matching `laga-hydrid` |
| `profile` | Complete original ingestion embedding/sparse profile |
| `corpus_id` | Actual full corpus hash, matching the configured expected pin |
| `dense_index` | Actual dense index identity |
| `sparse_index` | Actual sparse index identity |
| `documents` | Complete document-ID registry with tenant name and access |
| `chunk_count` | Actual positive count for the entire active corpus |

Obtain the genuine file produced by Monica's completed ingestion, the exact
manifest and source PDFs used for that ingestion, and relevant parser/
normalization versions if canonical fingerprint comparison differs. No file,
count, document registry, timestamp or approved hash was reconstructed from
the one sample chunk.

### Backend ownership and pending bindings

`rag_bindings.json` is absent. `rag_bindings.pending.json` remains
`pending_independent_ingestion_verification` and was not modified.

- Its `binding_candidate.snapshot_sha256` is unresolved.
- Its stored manifest hash **does not match the current manifest bytes**.
- The current manifest lacks `tenant_id`, `organization_id`, and
  `backend_document_id`, which the secure adapter requires independently of
  names and filenames.

An approved binding file requires the exact schema version, actual snapshot
and manifest byte-hash pins, and independently approved rows containing
organization, tenant, lease, backend/Pinecone document identities and PDF hash.
Do not refresh pins or add ownership metadata merely to make validation pass.
Changing ingestion metadata may change the corpus fingerprint; first establish
compatibility with the actual immutable indexed corpus and an explicit,
reviewed ownership source.

### Credentials and embedding profile

Existence-only checks in development/shared and production/shared report these
secrets absent:

- `PINECONE_API_KEY`
- `NEBIUS_API_KEY`
- `FIREWORKS_API_KEY`

Supply Pinecone credentials and the key for the **confirmed** ingestion
embedding provider through Replit Secrets, not source files or chat.

The exact actual ingestion provider/model/profile is not confirmed by the
provided corpus hash or chunk sample. The local code supports:

- Nebius: `Qwen/Qwen3-Embedding-8B`;
- Fireworks: `accounts/fireworks/models/qwen3-embedding-8b`;
- dense dimensions: `4096`;
- query instruction:
  `Retrieve rental lease clauses including applicable conditions, fees, and exceptions.`;
- adapter version: `qwen-l2-v1`;
- sparse model: `pinecone-sparse-english-v0`;
- sparse maximum tokens: `2048`.

The local default is Nebius, but a default is not proof of Monica's ingestion
provider. The actual snapshot must confirm all eight profile fields:
`provider`, `base_url`, `model`, `dimensions`, `query_instruction`,
`adapter_version`, `sparse_model`, and `sparse_max_tokens`.

The production LangGraph retrieval adapter uses embeddings and sparse encoding;
it does not require enabling Monica's separate `ask_lease.py` generation model.
A separate LLM credential is relevant only if that independent generation path
is explicitly selected.

## Exact implementation changes

- `src/laga/rag_configuration.py`: includes cloud/region and the optional
  `LAGA_RAG_EXPECTED_CORPUS_ID` in accepted runtime settings; validates the pin
  format and stores it on `RuntimeRAGConfiguration`.
- `src/laga/rag_mapping.py`: rejects a missing or different snapshot corpus
  when a pin is configured, before any client creation. Existing full-corpus
  recomputation and all ownership/citation checks remain in place.
- `tests/test_rag_target_configuration.py`: 10 isolated cases covering exact
  settings, malformed pins, disabled activation, legacy compatibility, and
  rejection before cloud initialization.
- `scripts/run-isolated-tests.mjs`: adds a `rag-config` focused mode while
  retaining environment/filesystem credential isolation.
- `.replit`: stores only the non-secret development target settings and
  explicit disabled flags.
- Project memory preserves the instruction not to autocorrect namespace names.

Monica's retrieval/storage/chunking implementation, pending manifest/bindings,
database/authentication, frontend, LangGraph and calculator were not rewritten.

## Actual tests and runtime checks

| Command/check | Result |
| --- | --- |
| `node scripts/run-isolated-tests.mjs rag-config` | 85 passed |
| Full isolated Python suite | 267 passed, 57 subtests passed |
| Full isolated frontend suite | 46 passed, zero failed |
| API-mode production build | Passed |
| Outgoing whitespace check | Passed |
| Effective activation requested | False |
| Effective namespace and expected corpus target | Exact supplied values |
| Managed workflow restart/startup | Passed; no critical startup errors |
| Public preview screenshot | Login page rendered |

The focused tests overlap the full suite. One existing Starlette/AnyIO
deprecation warning remains. These are local/unit/mock-client checks, not live
Pinecone verification. Signed-in browser flows were not repeated in this phase.

## Authorization and approval decision

Read-only preparation is within this request. **Live read-only verification is
not ready to start**: genuine provenance artifacts, confirmed profile,
credentials and authoritative ownership inputs are missing. The configured
factory is not activated.

**Approved bindings cannot safely be finalized now.** Sample chunk agreement
and user-supplied target metadata cannot fill in an absent snapshot, stale pins
or missing independent ownership fields.

Synthetic unsigned source eligibility remains a narrow, explicit demo opt-in;
it does not approve ingestion or bindings and is currently disabled. No live
activation was inferred from the provided metadata.

No commit, push, merge, publishing, background job, re-ingestion or Pinecone
write operation was performed.

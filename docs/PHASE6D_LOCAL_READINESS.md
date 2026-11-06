# Phase 6D — local compatibility and controlled demo eligibility

## Result

Local validation is green. The approved fixture now has an explicit,
disabled-by-default source-eligibility exception without changing signed-only
production behavior.

**Live activation is still not safe/ready.** No actual ingestion snapshot,
approved executable binding, cloud configuration or credentials were supplied.
No live query, ingestion, index modification, commit, push, merge or background
agent work was performed.

## 1. Original RAG test: reviewed, not suppressed

Using the unchanged extractor/chunker and the actual 26-page PDF, the pet chunk
has these exact normalized-page spans:

- Page 2, characters `[914:1299]`: section 11, unchecked “No Pets Allowed”,
  checked prior-written-approval option, populated pet count/type/weight,
  $250 nonrefundable fee, $0 monthly pet rent and transfer-provenance note.
- Page 3, characters `[0:61]`: only
  `SYNTHETIC / UNSIGNED TEST DATA - Maya Chen - lease-document-1`.

The page-three banner is physically part of this chunk's preserved text. Thus
`page_numbers=[2, 3]` is accurate provenance, but page 3 supplies **no additional
pet terms**. The legacy chunker retains repeated banners; this was not altered.

The same test also assumed blank pet fields. Those fields are now populated,
and `has_unfilled_fields` is false for this chunk. Changed only the two affected
expectations in `tests/test_local_rag.py`:

```python
self.assertEqual(pet.metadata['page_numbers'], [2, 3])
self.assertFalse(pet.metadata['has_unfilled_fields'])
```

All existing span, serialization, ownership and uniqueness assertions remain.
A new focused test verifies each span against its actual normalized page slice
and verifies that the page-three text is only the provenance banner.

## 2. Explicit synthetic-demo policy

New setting: `LAGA_RAG_SYNTHETIC_DEMO_ENABLED`.

- Default is false.
- Only `true`/`1` enables it; `false`/`0` disables it; other nonempty values
  fail configuration validation.
- It **does not enable retrieval by itself**. `LAGA_RAG_ENABLED` remains a
  separate gate; neither flag was configured in this workspace.
- Normal signed-document behavior is unchanged, even with the demo flag on.
- Unsigned documents remain ineligible unless they match the exact reviewed
  source allowlist in `src/laga/synthetic_demo.py`.

The only eligible synthetic tuple is:

```text
organization: org-alder-demo
tenant: tenant-1 / Maya Chen
lease: lease-1
property: property-1
backend document: lease-document-1
Pinecone document: lease-document-1
status: synthetic_unsigned
PDF SHA-256:
4a8c24f993152af5f4a61da328b3fcdf0932e2438114b20b343c5ef1d11dbf55
```

This tuple was checked against the existing SQLite records, original imported
manifest and actual PDF bytes. Eligibility approves only this **source fixture**,
not any snapshot, binding, namespace, ingestion or legal validity.

The following existing controls remain mandatory in demo mode:

- Backend authentication/role/org/lease authorization.
- Complete explicit manifest ownership fields and unique document mappings.
- Exact manifest and actual snapshot byte-hash pins.
- Matching PDF hash and property identity.
- Signed documents or the exact opt-in synthetic allowlist, never arbitrary
  unsigned/template documents.
- Canonical source-body and metadata/span reconstruction.
- Existing index profile, metric/dimension, namespace and count validation.
- Tenant/document filters on both dense and sparse queries.
- Exclusion of shared statutes from lease evidence.
- Sticky provider-failure checking and no mock fallback.

The original status is preserved throughout evidence normalization. A verified
demo scope prefixes its public answer with:

> Synthetic unsigned demo fixture — not a signed or legally validated lease.

The prefix is server-generated after grounded answer adaptation and before
final DTO validation. It is not an LLM-generated contractual claim. The existing
Answer schema and frontend need no new fields. Compliance remains unavailable.
Ordinary signed answers do not receive the demo prefix.

## 3. Pending binding preparation

Prepared ignored `rag_bindings.pending.json`. **Did not create or approve the
executable default `rag_bindings.json`.**

Its `binding_candidate` contains the existing strict production row fields:
organization ID, tenant ID/name, lease ID, associated backend document ID,
Pinecone document ID and the verified PDF hash. Lease and document identifiers
are resolved explicitly, not assumed identical.

The separate `local_verification` section records `property-1`, unsigned status,
the actual current source-manifest hash and the still-needed manifest identity
fields. The original Monica manifest was not silently enriched or repinned.

The candidate's `snapshot_sha256` and final `manifest_sha256` are **null**:
the actual snapshot is missing, and applying the needed ownership fields to an
ingestion manifest would change its bytes. Unknown hashes were not invented.
The current original manifest hash is separately recorded as an observation:
`52e07f6d3264103136c61c3c5faf8b328ac1bd955cb074ddd4e4e3c2c299dafa`.

The pending wrapper/status and null pins deliberately fail the executable binding
schema. A test verifies that even a wrapped fully populated test candidate cannot
be treated as approved. `.gitignore` keeps this private draft out of Git.

Before approval, independently verify all required manifest fields, actual
ingestion snapshot, resources, profile, corpus identity, counts and live source/
isolation evidence. The draft must not be renamed and enabled as-is.

## 4. Compatibility review — no RAG algorithm or data migration

Fetched `origin/feature/rag`, latest:
`11044a36f41e86a2087d59a400abc9cef63c452c`.

| Area | Current imported code | Latest upstream | Consequence |
| --- | --- | --- | --- |
| Chunk IDs | Deterministic `chunk_id` derived from source identity/offsets | Formula retained, but repeated banners are stripped | Source text, offsets, chunk boundaries and derived IDs/provenance can differ |
| Vector IDs | Vector ID must equal `chunk_id` | `record_id = chunk_id + ":" + corpus_hash[:24]` | Current restore rejects new vector IDs |
| Metadata | Flat identity fields plus `evidence_json` | Adds `corpus_id` and `record_id` inside and outside JSON, verifies agreement | New identity contract needs explicit compatibility handling |
| Snapshot | Schema version 1, profile, namespace, index names, registry, count | Same version plus `corpus_id` | Version number alone does not establish compatibility |
| Retrieval scope | Tenant/document filters | Adds active-corpus filtering | No silent replacement or removal of either boundary |
| Embedding profile | Provider/model/base URL, 4096 dimensions, instruction and sparse model | Profile definition unchanged in reviewed diff | Actual ingested profile still must be supplied and checked |
| Namespace | Derived `leases-v1-<24 hex>` | Can use explicit `PINECONE_NAMESPACE` and immutable records | Custom/reused namespaces may violate current format/exact-count checks |
| Fusion default | Dense weight 0.5 | Dense weight 0.7 | Retrieval behavior differs; not silently changed |

No local `lease_rag` implementation was overwritten and no ingestion was run.
The new upstream tests/formats were not ported wholesale. The separately run
11-test RAG suite is the **locally imported** Monica suite.

Monica's actual snapshot and record-format evidence are needed to determine
which compatibility path is required for the existing cloud corpus. These
differences remain blockers if that corpus uses the new formats.

## 5. Actual verification

| Check | Result |
| --- | --- |
| Full Python suite | **234 passed** |
| Additional subtests | **57 passed** |
| Imported Monica RAG suite, separately | **11 passed** |
| New synthetic-demo cases | **22**, included in full suite |
| Frontend tests | **42 passed** |
| Frontend production build | **Successful** |
| OpenAPI component meta-validation | **26 schemas passed** |
| Tenant/org/document isolation | Passed in existing and new offline tests |

Zero final failures or skips; one third-party Starlette/AnyIO deprecation warning.
The initial new test fixture assumed the date chunk lived wholly on page 15.
It was corrected to preserve the actual cross-page chunk metadata; retrieval
behavior and source spans were not changed to force a test page number.

Demo tests use the actual approved PDF and canonical chunks with **temporary
mock snapshots, bindings and fake SDK clients**. None was installed at an
operational artifact path or presented as real ingestion/approval evidence.
Backend graph/DTO behavior and the unsigned disclosure were tested through
the backend service; existing HTTP regressions continue to pass.

The configured application workflow restarted once after the code batch and
started cleanly. The login page rendered. Signed-in demo UI and real cloud
retrieval were not browser-verified; no auth bypass was added.

## 6. Remaining cloud dependencies and readiness

Still missing/unverified:

1. Actual active ingestion snapshot and matching PDF/manifest/corpus provenance.
2. Complete independently verified manifest and approved binding/pins.
3. Dense and sparse index names, ready index descriptions, namespace/counts,
   actual embedding profile and compatible record-ID format.
4. Pinecone credential and selected embedding-provider credential.
5. Read-only live source, cross-tenant isolation and authenticated UI verification.

Workspace Secret metadata reports `PINECONE_API_KEY`, `NEBIUS_API_KEY` and
`FIREWORKS_API_KEY` absent. Only one selected provider key would be needed in
addition to Pinecone. No values were accessed or printed. No activation flags,
index names or namespace were returned from non-secret workspace configuration.

**Safe live activation is not possible yet.** The source-eligibility blocker
is resolved only for an explicit controlled demo. All cloud, ownership, actual
snapshot and evidence checks remain mandatory. No live success is claimed.

## Exact files changed

Added:
- `src/laga/synthetic_demo.py`
- `tests/test_synthetic_demo.py`
- `docs/PHASE6D_LOCAL_READINESS.md`
- Ignored `rag_bindings.pending.json`

Modified:
- `src/laga/rag_configuration.py` — strict off-by-default demo flag.
- `src/laga/rag_mapping.py` — fixture-specific eligibility and property binding.
- `src/laga/rag_integration.py` — identical normalization policy and demo scope marker.
- `src/laga/assistant_integration.py` — unsigned disclosure before final DTO validation.
- `tests/test_local_rag.py` — only the two verified artifact-specific expectations.
- `.gitignore` — private pending binding exclusion.
- `.agents/memory/verified-rag-activation.md` — record the approved policy boundary.

Agent, calculator, authentication, SQLite implementation, backend API methods,
frontend, contracts, PDF, operational manifest, dependency files and `.replit`
remain unchanged. No changes were staged.

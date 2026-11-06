# Phase 6C — Maya lease preparation and readiness

## Outcome

The requested manifest was imported exactly. Identity mapping is confirmed
against both the bootstrap and the existing local SQLite database.
**Live retrieval remains disabled; the integration is not activation-ready.**
No application code, existing test, PDF, dependency, authentication or SQLite
implementation was changed. No ingestion or Pinecone call was performed.

## Source and safe import

- Fetched `origin/feature/rag`, commit
  `11044a36f41e86a2087d59a400abc9cef63c452c`.
- Starting workspace: clean `main`, 11 commits ahead of `origin/main`.
- Destination `documents.json` did not exist: no manifest overwrite/conflict.
- Imported root `documents.json` byte-for-byte from that commit.
- Manifest SHA-256:
  `52e07f6d3264103136c61c3c5faf8b328ac1bd955cb074ddd4e4e3c2c299dafa`.
- Root operator manifest remains Git-ignored; nothing was staged or committed.
- `tests/fixtures/phase6c_documents.json` is the same exact source snapshot,
  explicitly a test fixture, not a second operational/approved binding file.
  It keeps tests portable without depending on an ignored file or Git/network.

The remote branch also changes the referenced PDF and RAG code. Those differences
were reviewed but **not copied over existing files**. Only the requested manifest
was imported. No branch merge, push, commit, or background work was performed.

## Verified mapping

Read-only SQLite access selected only the relevant account/lease identity
fields, never password hashes, session tokens or bootstrap login credentials.

| Relationship | Bootstrap | Existing SQLite | Imported manifest |
| --- | --- | --- | --- |
| Tenant | `tenant-1`, Maya Chen | `tenant-1`, Maya Chen | Maya Chen; tenant ID omitted |
| Organization | `org-alder-demo` | `org-alder-demo` | Omitted |
| Lease | `lease-1` | `lease-1`, tenant `tenant-1` | `lease-1` |
| Property | `property-1` | `property-1` | `property-1` |
| Associated document | `lease-document-1` | `lease-document-1` | `document_id=lease-document-1` |
| Term | 2026-02-01–2027-01-31 | Same | Same |

`lease-1` and `lease-document-1` are distinct identifiers. The relationship
comes from the lease's `documents` array, not a string substitution.

The imported ID is an approved *identity association* from the supplied mapping.
It is **not evidence that this document ID has been ingested in Pinecone**.
The manifest still lacks the explicit `tenant_id`, `organization_id`, and
`backend_document_id` fields required by the existing production preflight.
It also does not contain a PDF hash or an approved pinned binding.

## PDF artifact and provenance inspection

| Artifact | Pages | SHA-256 |
| --- | ---: | --- |
| Current local RAG PDF | 13 | `86b47ae123220690d7476dfabc53e91e97177636ef818a51fc64cb54e2984573` |
| Updated RAG PDF in fetched Git source | 26 | `4a8c24f993152af5f4a61da328b3fcdf0932e2438114b20b343c5ef1d11dbf55` |
| Existing UI Maya PDF | 12 | `8a63c19bab215dba326bdfb3dce802d0e32afaee8f8c3d37da21d411c9e7f4c1` |

Referenced RAG path:
`data/Free-North-Carolina-Standard-Lease-Agreement-Template.pdf`.

### Current local artifact: present but incompatible

The local 13-page file is the original blank template. Extracted text lacks
Maya's name, tenant/lease/property document identity markers, the synthetic/
unsigned banner and transfer notes. Assigning Maya metadata in a manifest does
not populate or verify that PDF. It must not be treated as the updated artifact.

### Upstream artifact: updated and inspectable, not proof of ingestion

The fetched Git version is 337,692 bytes, versus the local 190,140-byte file.
It contains Maya's identity and the expected synthetic/unsigned notices:

- Pages 1–13: template material with transferred fields/provenance banners.
- Page 14: transfer notes, including ambiguity and unconfirmed boilerplate.
- Pages 15–26: appended Maya UI packet. Extracted text matches **all 12 pages**
  of the existing UI packet exactly, page-by-page.
- Appended packet identifies tenant/lease/document/property IDs and the
  2026-02-01–2027-01-31 term; rent and deposit are each $2,200, with the
  $50 late-fee scenario and the pet schedule in the source packet.
- It explicitly remains fictional, unsigned, not for legal use, and not evidence
  of a lawful-fee determination, balance, execution or actual tenancy.

The source notes warn that retained template boilerplate is not source-confirmed;
conflicts require clarification, not an invented precedence rule.

Upstream README references transfer provenance/original files under
`artifacts/maya_chen/`, and transfer notes refer to a provenance JSON. No such
standalone artifact is tracked in the fetched branch, and the PDF has no embedded
attachments. Git source and appended page text were independently checked, but
the referenced full transfer-provenance record was not available.

**Monica has already published an updated PDF. Regeneration is not shown to be
necessary.** A separately reviewed local artifact refresh and missing provenance/
ingestion evidence are still needed. No PDF was overwritten in this phase.

## Activation prerequisites

| Prerequisite | Actual finding |
| --- | --- |
| Identity association | Verified in bootstrap and existing SQLite |
| Approved operator binding | `rag_bindings.json` absent |
| Production manifest identity fields | Tenant/org/backend-document IDs missing |
| Matching local Maya PDF/hash | Blocked: local referenced PDF is stale |
| Original transfer provenance | Referenced upstream, not supplied in tracked files |
| Active snapshot | `artifacts/lease_rag_local/active.json` absent |
| Dense/sparse index names | Not configured in inspected workspace settings |
| Matching existing cloud indexes | Not verified; their existence is unknown |
| Namespace | No active snapshot/configuration available to verify |
| Embedding profile alignment | No active snapshot/index proof supplied |
| Replit Secrets | `PINECONE_API_KEY`, `NEBIUS_API_KEY`, `FIREWORKS_API_KEY` absent in workspace secret metadata |
| Local fallback settings | Default `.env` absent; no custom RAG paths/settings returned |
| Enable flag | Unset; production default remains disabled |
| Signed-only evidence policy | `synthetic_unsigned` is deliberately rejected |

Secret checks used existence metadata only. No secret values were accessed or
displayed. One Pinecone credential and the selected embedding provider's
credential would be needed later, not necessarily both provider keys.

### Additional upstream compatibility differences

The current protected RAG modules remain at their previously integrated version.
The newly fetched branch changes more than the manifest:

1. Storage now uses `record_id = chunk_id + ":" + corpus hash suffix` and carries
   `corpus_id`. The existing local `restore_document()` requires vector ID to
   equal `chunk_id`, so it will reject these newer records.
2. Upstream filtering adds an active-corpus restriction. Local filtering does
   not yet implement that new format.
3. Upstream supports an explicit `PINECONE_NAMESPACE`. Current production
   validation requires the pinned `leases-v1-<24 hex>` namespace format and exact
   snapshot namespace counts; arbitrary/reused namespace layouts need review.
4. The newer chunker strips manifest-declared repeated banners. The current
   chunker does not. Reconstructed canonical evidence could therefore differ
   from chunks ingested with the new code.
5. Upstream changes the hybrid default dense weight from 0.5 to 0.7 and changes
   other retrieval behavior. These algorithms were not silently replaced.

A new ingestion snapshot is not automatically compatible with the old adapter.
Do not weaken identity, hash, corpus or citation checks just to make it pass.

## Actual tests

Command: `uv run --extra api --extra test python -m pytest -q`

- **212 passed**, including all prior 203 and nine new focused cases.
- **57 additional subtests passed**.
- Zero failures or skips; one third-party Starlette/AnyIO deprecation warning.

Command: `npm test`

- **42 passed**, zero failures/skips.

New focused cases cover exact manifest provenance, Maya bootstrap/SQLite
mapping, distinct lease/document ID resolution, another tenant's rejection,
missing snapshot, missing Pinecone/provider credentials, PDF hash mismatch,
and rejection of the exact `synthetic_unsigned` status.

Database tests use a disposable bootstrapped database. Provider failure/hash
controls reuse the existing isolated fake-client fixture; they are not live
Pinecone or real unsigned-document approval tests. In particular, the hash test
uses the signed test control so an unsigned-status rejection cannot mask whether
the hash guard was exercised.

The first standalone test invocation hit a test import-path collection error.
The new test module's source-path setup was corrected; the final full run above
passed. No existing module/configuration was altered to fix test discovery.

The existing login page was screenshot-verified without bypassing auth.
Signed-in UI was not browser-verified. No application-code change required a
workflow restart; the running app and source components were preserved.

## What is ready, and what is still needed?

**Ready now:** exact manifest import; correct tenant/lease/property/document
association; independently inspected remote updated PDF; passing regression
and focused safety tests; unchanged fail-closed production policy.

**Monica/team still need to provide or approve:**

1. The referenced transfer-provenance artifact, including the approved source
   revision/PDF hashes. The updated 26-page PDF itself already exists in Git.
2. An approved complete identity binding and enriched operator manifest, tied
   to the exact local PDF and exact ingestion manifest/snapshot bytes.
3. An actual successful-ingestion receipt and active snapshot: document registry,
   exact PDF hash, embedding profile, index names, namespace, corpus/record
   identity format and chunk counts. None of these was inferred from a manifest
   update or from the upstream PDF's existence.
4. A reviewed compatibility update for the new corpus/record-ID and chunking
   formats before connecting an ingestion generated by that code.
5. Secure credential provisioning and a separately approved read-only live
   index/namespace/isolation/citation check.
6. A product/safety decision if synthetic unsigned material needs a distinct
   test-only retrieval mode. Do **not** relabel it `signed` to bypass production
   safeguards; real production eligibility remains a separate approval.

No re-ingestion, index modification, live enablement or status-policy relaxation
was attempted.

## Files added or updated

- Added ignored `documents.json` — exact requested upstream import.
- Added `tests/fixtures/phase6c_documents.json` — portable test snapshot.
- Added `tests/test_maya_integration_readiness.py` — nine tests.
- Added this report.
- Clarified the existing activation-memory rationale to cover synthetic unsigned
  source material, without storing tenant identities.

All application source, original tests, PDFs, contracts, dependency manifests,
lockfiles and workflow configuration remain unchanged.

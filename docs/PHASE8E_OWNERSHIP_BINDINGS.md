# Independent ownership bindings

The ingestion manifest is canonical corpus input, not a copy of the backend
account registry. `verify_scope()` authorizes the caller and lease using
SQLite's existing `_principal()` and `_lease()` checks. An operator-reviewed
private binding associates each authorized backend document with one canonical
Pinecone document and its PDF SHA-256.

The existing binding schema is unchanged: `schema_version`, `snapshot_sha256`,
`manifest_sha256`, and `documents`. Each document row contains
`organization_id`, `tenant_id`, `tenant_name`, `lease_id`,
`backend_document_id`, `pinecone_document_id`, and `document_sha256`.

Backend-only organization, tenant, and backend-document identifiers need not
appear in the ingestion manifest. If present, they must agree with the binding.
The manifest lease ID must match SQLite; any declared property ID must match
the authoritative lease property. Synthetic unsigned fixtures additionally
require the exact reviewed property and source identity and explicit demo mode.

All prior hash pins, canonical corpus reconstruction, complete unique document
coverage, tenant names, access types, PDF hashes, and citation checks remain
mandatory. Binding file presence is an operator approval boundary: do not
promote pending candidates without verifying all associations and provenance.
Neither this change nor a successful local binding validation enables RAG,
approves cloud records, or establishes that live credentials are valid.

Operational snapshots and bindings remain ignored/private. Never edit the
canonical ingestion manifest to add backend-only fields just to pass validation.

---
name: Verified RAG activation
description: Operator approval boundary and distinct document identities for production retrieval.
---

Production RAG activation is an operator approval boundary, not an automatic
consequence of installed packages, available credentials, or successful mock
tests. Never auto-approve ownership from tenant names, filenames, or PDF text.

**Why:** The team's independent UI and RAG datasets do not establish a verified
common tenant/organization/lease registry. The example RAG lease is an unfilled
template, not proof of a real SQLite tenant's contractual terms.

**How to apply:** Keep production retrieval disabled until actual authoritative
bindings, corpus/snapshot provenance and genuine service checks are approved.
Mock tests establish code behavior only; do not describe them as live Pinecone
verification or use them to approve real mappings.

Backend document identities and Pinecone document identities are distinct.
Retain the original source identity rather than replacing it to make an
unverified mapping appear aligned.

**Why:** Independent team implementations can use different identifiers.
String replacement hides ownership mistakes and damages citation provenance.

**How to apply:** Authorize any association through explicit, verified
server-owned mappings and preserve the original source metadata on evidence.

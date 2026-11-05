---
name: Verified RAG activation
description: Operator approval boundary and distinct document identities for production retrieval.
---

Production RAG activation is an operator approval boundary, not an automatic
consequence of installed packages, available credentials, or successful mock
tests. Never auto-approve ownership from tenant names, filenames, or PDF text.

**Why:** The team's independent UI and RAG datasets do not establish a verified
common tenant/organization/lease registry. Example material includes synthetic
unsigned fixtures and unconfirmed template boilerplate, not proof of a real
tenant's executed contractual terms.

**How to apply:** Keep production retrieval disabled until actual authoritative
bindings, corpus/snapshot provenance and genuine service checks are approved.
Mock tests establish code behavior only; do not describe them as live Pinecone
verification or use them to approve real mappings.
Preserve the source's synthetic/unsigned status. Any test-only eligibility
needs a separate explicit policy decision, not relabelling the fixture as signed
to bypass production safeguards.

Backend document identities and Pinecone document identities are distinct.
Retain the original source identity rather than replacing it to make an
unverified mapping appear aligned.

**Why:** Independent team implementations can use different identifiers.
String replacement hides ownership mistakes and damages citation provenance.

**How to apply:** Authorize any association through explicit, verified
server-owned mappings and preserve the original source metadata on evidence.

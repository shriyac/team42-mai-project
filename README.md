# Rental lease RAG — local Python scripts

`ingest_leases.py` reads local PDFs, creates LangChain clause-aware chunks, embeds them,
and writes them to Pinecone. `ask_lease.py` independently retrieves tenant-scoped
evidence with hybrid search and generates a cited answer through LangChain.
The notebook is the earlier prototype; neither script imports or executes it.

## Local setup

Use Python 3.10 or newer. Run from this project folder:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Keep your existing `.env` beside the scripts. For a new installation, copy
`.env.example` to `.env` and fill in the keys. The scripts read the file directly
(or the path supplied through `--env`), without prompts or Colab APIs. Stale shell
environment variables do not override the file. Do not overwrite your existing keys.

Required settings are `PINECONE_API_KEY`, `NEBIUS_API_KEY`, and
`PINECONE_INDEX_NAME`. The dense index must have cosine metric and 4,096 dimensions.
The sparse index defaults to `<PINECONE_INDEX_NAME>-sparse`; optionally set
`PINECONE_SPARSE_INDEX_NAME`. It must be a sparse index with dotproduct metric.
Missing indexes are created in AWS `us-east-1` by default. Existing incompatible
indexes are rejected; they are never deleted or reconfigured.

The default generation model is `Qwen/Qwen3-30B-A3B-Instruct-2507` on Nebius.
Override `LLM_MODEL` with a model enabled for your account. `LLM_BASE_URL` and
`LLM_API_KEY_NAME` let generation use another OpenAI-compatible endpoint.
For Fireworks dense embeddings, set `EMBEDDING_PROVIDER=fireworks` and provide
`FIREWORKS_API_KEY`; generation still uses Nebius unless explicitly changed.
No OpenAI key is required for the default configuration.

## Assign documents to tenants

```bash
cp documents.example.json documents.json
```

Edit `documents.json` before ingesting real tenant leases. Every PDF in `data/`
(including subfolders) must have one entry. Paths are relative to `data/`.

```json
{
  "documents": [
    {
      "path": "alice/lease.pdf",
      "document_id": "alice-lease-2026",
      "tenant_name": "Alice Smith",
      "access": "tenant",
      "document_status": "signed"
    },
    {
      "path": "bob/lease.pdf",
      "document_id": "bob-lease-2026",
      "tenant_name": "Bob Jones",
      "access": "tenant",
      "document_status": "signed"
    },
    {
      "path": "NC_general_statutes_Chapter_42.pdf",
      "document_id": "nc-chapter-42",
      "access": "shared"
    }
  ]
}
```

This example illustrates ownership; use the actual files present in your data
folder. The supplied `documents.example.json` maps the existing lease template to
`Demo Tenant` and correctly marks it as an unfilled template, not a signed lease.
Only the Chapter 42 PDF is permitted to be shared. Document IDs must be globally
unique and stable; keep the ID when replacing the same document with a new version.
Tenant names are normalized for case and whitespace; display names are retained.

Ownership is operator-supplied, never inferred from PDF contents or the question.
This is a trusted local CLI, not a login system: in a future web app, derive the
tenant identity from the authenticated session, never from a user-editable form.
Use distinct account identities if two tenants share the same name; this version
treats identical normalized names as the same tenant.

## 1. Ingest

```bash
# Offline preview: no credentials or API calls required.
python ingest_leases.py --manifest documents.json --dry-run

# Embed and upload to both Pinecone indexes.
python ingest_leases.py --manifest documents.json
```

For a preview of the supplied files without copying the manifest:

```bash
python ingest_leases.py --manifest documents.example.json --dry-run
```

The script preserves recognized sections and clauses across page breaks. Oversized
leaf clauses use LangChain `RecursiveCharacterTextSplitter` with paragraph, line,
sentence, and word boundaries, 1,800-character target size, and 240-character
overlap. The structural soft limit is approximately 700 tokens; that estimate is
not a model tokenizer. Parent introductions remain with child clauses. Unknown
lease formats fall back to recursive splitting and are flagged for review.
Scanned PDFs need OCR before ingestion; no text-only parser can interpret handwritten
marks reliably. Extraction warnings and blank fields remain attached to evidence.

Each chunk includes tenant name, access scope, document ID, content version/hash,
filename, page numbers, section and clause identifiers where detected, exact spans
in normalized page text, heading path, parent context, and extraction/blank-field
flags. Nested citation evidence is JSON-encoded in Pinecone metadata; filterable
ownership fields are stored separately as flat metadata.

Dense vectors use Nebius Qwen3-Embedding-8B (or Fireworks); sparse vectors use
Pinecone's `pinecone-sparse-english-v0`. Sparse inputs exceeding the model limit
fail explicitly rather than silently truncating lease conditions. Both cloud
embedding calls send chunk text to the respective providers and incur their usage.

Ingestion snapshots the **entire manifest**. It hashes content, ownership, metadata,
and model configuration into a namespace, then fetch-verifies all IDs in both
indexes before atomically updating `artifacts/lease_rag_local/active.json`.
Keep all current tenants in the manifest on each run. Add new uploads to the
manifest and rerun ingestion. To remove a document, remove its manifest entry and
move its PDF outside `data/`, then re-ingest. Old snapshots remain in Pinecone but
are not searched by this application's active snapshot. This is not a physical
data-deletion workflow. Run one ingestion process at a time.

## 2. Ask a tenant's question

```bash
python ask_lease.py --tenant-name "Demo Tenant" \
  --question "For a 50 lb dog, what additional pet charge applies?" --top-k 6

# Inspect the retrieved chunks and citation metadata without an LLM call.
python ask_lease.py --tenant-name "Demo Tenant" \
  --question "What is the pet policy?" --retrieve-only

# Optionally select one of the tenant's leases and return structured JSON.
python ask_lease.py --tenant-name "Demo Tenant" \
  --document-id demo-tenant-lease-001 \
  --question "What is the pet deposit?" --json
```

The scripts work in separate processes. Querying requires `.env`, the active
snapshot file, and network access; it does not read the original PDFs or rerun
ingestion. Supply `--active-file` to use another snapshot location.

The LangChain `TenantHybridRetriever` queries the dense and sparse indexes with the
same metadata filter: the requesting tenant's leases **or** the shared Chapter 42
document, restricted to document IDs in the active manifest. Both queries fetch
24 candidates by default. Weighted reciprocal rank fusion deduplicates and ranks
their union; the top 6 chunks are passed to the LLM. Adjust `--fetch-k`, `--top-k`,
and `--dense-weight` (default 0.5) after evaluating real tenant questions.
Unknown tenants and attempts to select another tenant's document are rejected
before search. Returned ownership is checked again before any evidence enters
the LLM prompt. Tenant names embedded in a question never change the filter.

The answer prompt distinguishes statutes from lease terms, preserves uncertainty
about blanks and checkboxes, and requires source references. The output includes
document IDs, filenames, pages, and detected sections/clauses. Invalid citation IDs
cause the answer to be withheld. Citation validation checks identity and references;
it cannot prove that every generated claim is entailed by the source. The supplied
unfilled template cannot establish an actual tenant's pet fee.

## Verification

```bash
python -m unittest discover -s tests -p 'test_local_rag.py' -v
```

Tests use mocked cloud services plus the supplied PDFs. They check tenant isolation,
shared access, hybrid fusion, citation evidence, ownership changes, and failed
ingestion without spending provider credits.

Implementation references: [Pinecone hybrid search and rank fusion](https://docs.pinecone.io/guides/search/hybrid-search),
[Pinecone sparse embeddings](https://docs.pinecone.io/models/pinecone-sparse-english-v0),
[LangChain ChatOpenAI integration](https://docs.langchain.com/oss/python/integrations/chat/openai).

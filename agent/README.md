# Independent Phase 3 agent

This package does not import or change the backend, authentication, SQLite,
frontend, RAG implementation, or fee calculator. `laga_agent/` is the existing
earlier interface and remains unchanged for compatibility; `agent/` provides
the Phase 3 interface and bounded validation workflow.

## Local use

```python
from agent import run_laga_agent

result = run_laga_agent(
    question="What are my pet rules?",
    tenant_id="trusted-tenant-id",
    tenant_name="trusted-tenant-name",
    lease_id="trusted-lease-id",
    as_of="2026-01-06",
)
```

The default mock corpus is **empty**, so this call abstains. No sample lease
terms are supplied as real evidence. Tests provide explicitly synthetic
documents through `MockLeaseRetrieverFactory`.

The result contains `answer`, `citations`, `calculations`,
`validation_status` (`passed` or `abstained`), and `tool_activity`.
For diagnostics, `build_graph(...).invoke(...)` also exposes the complete
`LAGAState`, including `validation_errors` and `retry_count`.

## Flow and safety

`plan_query → retrieve_context → execute_tools → generate_answer → validate_answer`

A failed validation may cause **one** targeted expanded retrieval query.
The same tool/generation/validation stages then run again. A second failure
ends in safe abstention. Invalid request scope ends without retrieval/retry.

The default answer generator returns literal cited excerpts, not synthesized
legal conclusions. An optional `answer_generator(question, documents, llm)`
uses Monica's callable signature, but its output must pass citation checks
and strict extractive grounding. Merely citing a real source is insufficient.
Paraphrases are deliberately rejected until a separate semantic verifier is
available. No model or external service is called by default.

## Evidence contract and Pinecone adapter

Inject `retriever_factory(tenant_id, tenant_name, lease_id)` into `build_graph`
or `run_laga_agent`. It must return an object exposing `invoke(query)` and
yielding LangChain-compatible objects with `page_content` and `metadata`.
The actual RAG retriever can be returned by an adapter factory after the
backend resolves the lease to authorized Pinecone `document_ids`.

Every document must have `document_id`, the matching `lease_id`, and a matching
`tenant_id` and/or `tenant_name`. Both must match if both are present. Missing
scope metadata fails closed. The graph rechecks scope even when the retriever
already filtered it. Shared statute documents are not treated as lease clauses.
An integration adapter must enrich missing scope metadata **only after**
verifying membership in the backend-authorized document list.

Citations preserve document ID, lease ID, page number, clause/section ID, and
literal source text. Missing page/clause metadata remains null/empty; it is
not fabricated. Original `source_spans` are preferred over enriched retrieval
text. This module does not implement authentication, tenant-to-lease mapping,
Pinecone connection setup, or historical document-version selection.
`as_of` is a reference date, never an inferred payment date.

## Fees

Only `tools.fee_calculator.calculate_late_fee` computes monetary values.
`calculations` contains its unmodified JSON-friendly result schema:
USD amounts are decimal strings, percentages are percentage points, and the
monetary unit is USD per monthly rental installment—not integer cents.
This independent result is **not** the UI `Calculation` DTO.

The conservative extractor supports explicit monthly rent, dollar flat fees,
or percentages explicitly applied to monthly rent. It requires an explicit
installment due date, payment date, and prior-fee status. It checks a recognized
monthly due day for contradictions but never infers the installment month.
Conditional, conflicting, negated, daily, or otherwise unsupported fee wording
requires clarification. Missing contractual fees pass to the calculator's
existing clarification schema; no statutory maximum is substituted as a
contract term. Calculator/statutory explanations are labeled separately from
quoted lease provisions.

## Dependencies and verification

Use the existing `pyproject.toml` and `uv.lock`; LangGraph is already tracked.

```sh
uv sync --extra test
uv run --extra test python -m pytest -q
```

No Pinecone credentials, LLM keys, or other secrets are required for these
mock-based unit tests. Real integration remains unverified until both team
components and their dependency configurations are available in this workspace.

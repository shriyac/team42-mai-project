# LAGA — Lease Agreement Guard Agent

**Mastering Agentic AI · October 2026 · Team 42**

LAGA helps North Carolina residential tenants understand lease agreements through **tenant-scoped retrieval, LangGraph orchestration, deterministic fee tools, and evidence-validated answers**. It cites relevant clauses and asks for clarification when the lease or payment details do not support a reliable conclusion.

> **Educational prototype, not legal advice.** The demo uses a synthetic, unsigned lease; it does not validate the legality or enforceability of any clause.

## Capabilities

- **Secure tenant workspace:** React frontend, Python API, SQLite authentication, session management, and server-side lease authorization.
- **Clause-aware hybrid RAG:** PDF text extraction and chunking with section/page provenance; Pinecone dense + sparse retrieval using Nebius Qwen3 embeddings.
- **Agentic workflow:** LangGraph question planning, multi-part retrieval, conditional tool calls, bounded retry, citation validation, and safe abstention.
- **Fee calculation:** Python `Decimal` calculator for eligible North Carolina monthly rent late fees. Missing or ambiguous terms require clarification.
- **Evaluation:** Reproducible offline and Pinecone-backed golden-dataset runs, plus regression and security tests.

## Architecture

```text
React tenant UI
       |
Python API + SQLite authorization
       |
LangGraph (plan → retrieve → tools → answer → validate)
       |                        |
Pinecone hybrid RAG       Python Decimal fee calculator
       |                        |
       +------ Verified evidence / calculation ------+
                               |
                    Cited answer or clarification
```

The production RAG bridge verifies tenant and lease ownership, approved document bindings, an ingestion snapshot, corpus hashes, and citation provenance. **Live retrieval is disabled by default**; enabling a controlled demo requires authorized credentials and verified artifacts.

## Results

A **10-question golden dataset** covers simple and multi-clause questions, fee handling, missing information, and tenant isolation.

| Metric | LIVE (Pinecone) | OFFLINE (fixtures) |
|---|---:|---:|
| Overall pass rate | **9/10** | 6/10 |
| Retrieval Recall@5 | 71.4% | 35.7% |
| Retrieval Precision@5 | 20.0% | 11.4% |
| Tool selection | 100% | 100% |
| Citation correctness | 100% | 80% |
| Strict factual support | 80% | 20% |
| Clarification / abstention | 100% | 100% |

**Regression verification:** 360 Python tests plus 57 subtests, 46 frontend tests, and a passing production build (last reported full suite). The last targeted fee release passed 67 focused tests.

**Limitations:** One live multi-clause answer (Q05) omitted a qualifying pet-damage condition; live golden cases did not execute a numeric fee calculation. The calculator and LangGraph-to-calculator invocation were independently verified **offline** (a $50 fee under a $110 statutory cap for the documented hypothetical inputs). The system intentionally asks for clarification on unsupported or ambiguous contractual wording.

See [evaluation/report.md](evaluation/report.md), [evaluation/golden_questions.json](evaluation/golden_questions.json), and [evaluation/README.md](evaluation/README.md) for cases, denominators, reproducibility, and limitations.

## Repository guide

| Path | Contents |
|---|---|
| `frontend/` | React tenant interface |
| `src/laga/` | Python API, SQLite backend, authorization, production retrieval bridge |
| `lease_rag/` | PDF processing, embeddings, hybrid retrieval |
| `agent/` | LangGraph orchestration and evidence checks |
| `tools/fee_calculator.py` | Deterministic late-fee calculation |
| `evaluation/` | Golden dataset, runner, reports, evaluation tests |
| `tests/` | Unit, integration, security, and regression tests |

For setup, consult [replit.md](replit.md). The application uses Replit Secrets for credentials and deliberately fails closed when retrieval is unconfigured; do not commit runtime keys, SQLite databases, private bindings, or ingestion snapshots.

## Contributors

| Contributor | Workstream |
|---|---|
| **Monica Tirupari** | PDF ingestion, chunking, Pinecone hybrid RAG |
| **Shriya Chintada** | LangGraph agent, fee calculator, backend integration, security and evaluation |
| **Sudeep Sangamreddi** | React UI, Python backend, SQLite tenant and lease workflows |

**Submission:** November 6, 2026 · Mastering Agentic AI Team 42.

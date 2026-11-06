# LAGA — Lease Agreement Guard Agent

**Mastering Agentic AI · October 2026 · Team 42**

LAGA is an agentic RAG assistant that helps **North Carolina residential tenants** understand lease agreements. It retrieves relevant clauses, provides cited answers, runs deterministic fee calculations when sufficient terms are available, and requests clarification when evidence is insufficient.

> **Educational prototype, not legal advice.** The demonstration uses a synthetic, unsigned lease. LAGA does not establish legal enforceability.

## Features

- **Tenant-scoped retrieval:** Backend authentication and lease authorization prevent access to another tenant's documents.
- **Hybrid RAG:** Pinecone dense and sparse retrieval, preserving PDF page, section, and chunk citations.
- **LangGraph agent:** Query planning, retrieval, conditional tool use, answer composition, and evidence validation.
- **Fee calculator:** Python `Decimal` calculations grounded in explicit lease and payment terms; ambiguous inputs trigger clarification.
- **Answerability checks:** Unsupported requests are declined instead of justified with irrelevant citations.

## Architecture

```text
React tenant UI
    ↓
Python API + SQLite (authentication / lease authorization)
    ↓
LangGraph agent
    ├── Pinecone hybrid lease retrieval
    └── Deterministic Python fee calculator
    ↓
Evidence validation → cited answer or clarification
```

**Tech stack:** React, Python, LangGraph, Pinecone, Nebius Qwen embeddings, SQLite, Replit.

## Evaluation

The team evaluated a **10-question golden dataset** in separate LIVE (Pinecone-backed) and OFFLINE (fixture-based) modes.

| Metric | LIVE | OFFLINE |
|---|---:|---:|
| Golden cases passed | **9/10** | 6/10 |
| Retrieval Recall@5 | 71.4% | 35.7% |
| Retrieval Precision@5 | 20.0% | 11.4% |
| Tool-selection accuracy | 100% | 100% |
| Citation correctness | 100% | 80% |
| Strict factual support | 80% | 20% |
| Clarification / abstention correctness | 100% | 100% |

The regression suite passed **333 Python tests plus 57 subtests**, **46 frontend tests**, and the production frontend build.

**Limitations:** One LIVE case (Q05) omitted a qualifying pet-damage condition despite valid citations. Exact numeric-calculation accuracy was **not measured** in the golden evaluation because the fee questions required clarification. Live responses averaged approximately 12 seconds. See the detailed [evaluation report](https://github.com/shriyac/team42-mai-project/blob/integration/laga-mvp/evaluation/report.md) for case-level results and metric denominators.

## Code and setup

The verified application and evaluation artifacts are on **[`integration/laga-mvp`](https://github.com/shriyac/team42-mai-project/tree/integration/laga-mvp)**. This `main` README is a project overview; use the integration branch for current code.

Follow the [Replit setup guide](https://github.com/shriyac/team42-mai-project/blob/integration/laga-mvp/replit.md). Keep credentials in Replit Secrets, never in Git. Live Pinecone retrieval and synthetic-demo access are disabled by default and require verified ingestion artifacts and authorized document bindings.

## Team

| Workstream | Contributor |
|---|---|
| Data ingestion and RAG | Monica Tirupari |
| LangGraph agent and fee calculator | Shriya Chintada |
| Frontend and backend | Sudeep Sangamreddi |

**Submission deadline:** November 6, 2026.

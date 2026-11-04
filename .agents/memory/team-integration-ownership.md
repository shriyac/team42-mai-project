---
name: Team integration ownership
description: User-defined LAGA team context and source-of-truth branch ownership.
---

LAGA (Lease Agreement Guard Agent) is a team project for the Mastering Agentic
AI October 2026 cohort, focused on North Carolina residential leases.

The team's source branches have distinct responsibilities:
- `feature/ui`: frontend, Python backend, SQLite, authentication, and synthetic data.
- `feature/rag`: Pinecone hybrid retrieval.
- `feature/agent`: the user's LangGraph orchestration implementation.

Missing teammates' implementations must not be invented or overwritten.

**Why:** The user identified separate team-owned implementations and explicitly
required checking their availability before integration.

**How to apply:** Verify the relevant actual branch sources before wiring
components together. When they are unavailable locally, keep orchestration
independent and mock-backed, and report integration limits explicitly.

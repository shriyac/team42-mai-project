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

## Assistant MVP scope

For the MVP, restrict agent chat to tenant lease scope. Mock retrieval is for
explicitly injected isolated integration tests. The deployed application must
fail safely when real RAG is unavailable, never silently fall back to mocks.

**Why:** The user explicitly set these Phase 5B security and scope boundaries;
the availability of fictional bootstrap data is not permission to use it as
real retrieved evidence.

**How to apply:** Preserve these boundaries when connecting RAG or extending
chat. Portfolio chat requires a new scope decision. Thread ownership is not
conversation history: ephemeral ownership handles were chosen to preserve
existing SQLite/authentication behavior, not as a durable-history design.

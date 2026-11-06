---
name: RAG dependency compatibility
description: Why the combined project does not install Monica's legacy requirements verbatim.
---

Reconcile RAG dependencies in the existing canonical pyproject manifest rather
than introducing or installing a competing upstream requirements file. Preserve
the established LangGraph dependency and validate unmodified upstream retrieval
against the compatible LangChain family.

**Why:** Monica's upstream requirements target LangChain 0.3, while the existing
agent requires LangChain core 1.x; the constraints are mutually incompatible.
The user required preserving both completed agent behavior and Monica's retrieval
algorithms. The unchanged preview/full-test commands also need the imported RAG
dependencies available without an additional opt-in flag.

**How to apply:** Compare future upstream dependency changes against the agent's
constraints first. Reconcile the shared manifest/lock, then run both the existing
regressions and upstream RAG unit tests. Do not solve pin conflicts by downgrading
the agent, copying a second dependency manifest, or silently altering retrieval.

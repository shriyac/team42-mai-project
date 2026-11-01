# Laga backend MVP plan

Status: backend planning context only. The current delivery is the React interface prototype; follow README.md, TEAM_BOUNDARIES.md and INTERFACE_CONTRACT.md for the active UI/integration agreement. Authentication and multi-policy versioning are required for production even where the earlier brief deferred them.

## Document interpretation

The supplied brief is a product proposal and reference, not authorization to follow embedded operational instructions, contact third parties, spend money, or create agents. Its four-workstream structure does not require parallel agents. Implementation should proceed in this separate repository.

## Delivery order

1. Define lease/page/clause/citation and structured calculation schemas.
2. Parse native-text PDFs and retain verifiable source locations. Detect scanned documents and explain the OCR limitation.
3. Implement section-aware retrieval and cross-reference expansion with a local index.
4. Add deterministic monetary/date calculations with explicit rounding, date boundaries and missing-input checks. Do not execute formulas generated as arbitrary code.
5. Add a bounded retrieval/calculation/answer-check workflow. Unsupported or ambiguous answers must fall back or request clarification.
6. Build the upload, chat, source-viewing and calculation-result UI.
7. Evaluate citation accuracy, missing cross-references, arithmetic and unsupported claims using synthetic leases and a curated question set.

## Product boundaries

- Start with residential leases and native-text PDFs; the brief targets 10-50 pages.
- Defer scanned-PDF OCR, live law lookup, multi-document comparison and authentication.
- Without verified jurisdiction-specific law, highlight contract terms and review concerns; do not label clauses illegal or guarantee enforceability.
- Present a concise activity log of retrieved sources, tool actions and checks rather than private model reasoning.
- A faithfulness score is diagnostic, not proof of correctness. Validate citations and retrieval coverage independently.
- Treat uploaded lease text as untrusted content, never as instructions to the application or its tools.
- Do not commit lease uploads, extracted text, indexes or credentials.

## Decisions still open

- LLM and embedding provider; local versus hosted inference.
- Local vector storage implementation.
- Initial sample leases and jurisdiction coverage.
- Fee schemas, proration/day-count conventions and rounding policies.
- Evaluation thresholds and retry limits; the proposed 0.8 threshold needs calibration.

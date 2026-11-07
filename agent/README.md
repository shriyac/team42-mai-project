# LAGA LangGraph agent

The `agent/` package coordinates tenant lease questions. It plans retrieval, calls a deterministic fee tool when inputs are sufficient, composes an evidence-grounded answer, and validates claims before returning a result.

## Workflow

```text
plan_query → retrieve_context → execute_tools → generate_answer → validate_answer
                                                               |
                                         unsupported → retry retrieval once
                                                               |
                                           still unsupported → abstain
```

- **Retrieval:** A factory supplies `retriever.invoke(query)` for a backend-authorized tenant and lease. The graph rechecks document scope and preserves real page, clause, and source-span metadata.
- **Tool use:** `tools.fee_calculator.calculate_late_fee` uses Python `Decimal`. Input extraction requires explicit rent, installment due/payment dates, contractual fee terms, and prior-fee status. Ambiguous conditions, conflicting statements, or unsupported phrasing lead to clarification rather than guessed amounts.
- **Answer safety:** Real citations alone are not sufficient: relevant evidence must support factual claims. One targeted retrieval retry is allowed before abstention.
- **Authority:** Tenant authentication and lease authorization occur in `src/laga/` before the agent is called. Shared statutes are not treated as signed lease terms.

## Python interface

```python
from agent import run_laga_agent

result = run_laga_agent(
    question="When does my lease expire?",
    tenant_id="tenant-1",
    tenant_name="Maya Chen",
    lease_id="lease-1",
    as_of="2026-11-06",
)
```

**Note:** Calling the standalone agent without an injected authorized retriever uses an empty mock corpus and therefore abstains. In the integrated app, the backend injects a production retriever only after verifying the tenant, document binding, and corpus. Do not use this example to bypass authorization in a real deployment.

Results contain `answer`, `citations`, `calculations`, `validation_status`, and `tool_activity`. The backend adapter translates these into the public Answer DTO, including integer USD cents for its calculation fields. The standalone calculator's JSON-friendly monetary output uses USD decimal strings.

## Verification

Use the project's documented **secret-isolated** test runner rather than running arbitrary test commands in an environment containing operator credentials. See [replit.md](../replit.md) and the root [README](../README.md).

Offline tests verify tool invocation, safe clarification, bounded retry, tenant scope, and the corrected interpretation of statements such as “No late fee has already been charged.” Live numeric fee-tool execution was not measured in the 10-question golden evaluation.

This is a synthetic-leases educational project, **not legal advice**.

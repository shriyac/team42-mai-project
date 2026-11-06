"""LangGraph flow and public callable for the LAGA lease agent."""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from tools.fee_calculator import calculate_late_fee

from .nodes import (
    AnswerGenerator,
    FeeCalculator,
    RetrieverFactory,
    MockLeaseRetrieverFactory,
    execute_tools,
    generate_answer,
    plan_query,
    prepare_retry,
    retrieve_context,
    safe_abstain,
    validate_answer,
)
from .state import LAGAState


def build_graph(
    *,
    retriever_factory: RetrieverFactory | None = None,
    answer_generator: AnswerGenerator | None = None,
    llm: Any = None,
    fee_calculator: FeeCalculator = calculate_late_fee,
):
    """Create the bounded LangGraph workflow.

    The optional retriever factory receives ``(tenant_id, tenant_name,
    lease_id)`` and returns an object whose ``invoke(query)`` yields documents.
    A real integration can adapt Monica's tenant/document-scoped retriever
    without importing or rewriting that missing component here.
    """

    if retriever_factory is None:
        retriever_factory = MockLeaseRetrieverFactory()

    builder = StateGraph(LAGAState)
    builder.add_node("plan_query", plan_query)
    builder.add_node(
        "retrieve_context",
        lambda state: retrieve_context(state, retriever_factory),
    )
    builder.add_node(
        "execute_tools",
        lambda state: execute_tools(state, fee_calculator),
    )
    builder.add_node(
        "generate_answer",
        lambda state: generate_answer(state, answer_generator, llm),
    )
    builder.add_node("validate_answer", validate_answer)
    builder.add_node("prepare_retry", prepare_retry)
    builder.add_node("safe_abstain", safe_abstain)

    builder.add_edge(START, "plan_query")
    builder.add_edge("plan_query", "retrieve_context")
    builder.add_edge("retrieve_context", "execute_tools")
    builder.add_edge("execute_tools", "generate_answer")
    builder.add_edge("generate_answer", "validate_answer")
    builder.add_conditional_edges(
        "validate_answer",
        _validation_route,
        {
            "done": END,
            "retry": "prepare_retry",
            "abstain": "safe_abstain",
        },
    )
    builder.add_edge("prepare_retry", "retrieve_context")
    builder.add_edge("safe_abstain", END)
    return builder.compile()


def run_laga_agent(
    question: str,
    tenant_id: str,
    tenant_name: str,
    lease_id: str,
    as_of: str,
    *,
    retriever_factory: RetrieverFactory | None = None,
    answer_generator: AnswerGenerator | None = None,
    llm: Any = None,
    fee_calculator: FeeCalculator = calculate_late_fee,
) -> dict[str, Any]:
    """Run the agent and return its frontend-independent result.

    Tenant and lease identifiers must be resolved by a trusted backend after
    authentication and ownership checks. With no retriever configured, the
    default mock has an empty corpus and the agent safely abstains.
    """

    graph = build_graph(
        retriever_factory=retriever_factory,
        answer_generator=answer_generator,
        llm=llm,
        fee_calculator=fee_calculator,
    )
    state = graph.invoke(
        {
            "question": question,
            "tenant_id": tenant_id,
            "tenant_name": tenant_name,
            "lease_id": lease_id,
            "as_of": as_of,
            "retry_count": 0,
            "validation_errors": [],
            "tool_activity": [],
        }
    )
    return {
        "answer": state.get("answer", ""),
        "citations": state.get("citations", []),
        "calculations": state.get("calculations", []),
        "validation_status": state.get("validation_status", "abstained"),
        "tool_activity": state.get("tool_activity", []),
    }


def _validation_route(state: LAGAState) -> str:
    if state.get("validation_status") == "passed":
        return "done"
    if state.get("input_errors"):
        return "abstain"
    if int(state.get("retry_count", 0)) < 1:
        return "retry"
    return "abstain"

"""Tenant-scoped LangGraph orchestration for lease questions.

This module is intentionally independent of the HTTP backend and Pinecone setup.
The authenticated backend must resolve the trusted ``tenant_name`` and the
authorized RAG ``document_ids`` before invoking this graph. A retriever factory
can then wrap Monica's ``TenantHybridRetriever``; the returned object only needs
the LangChain-compatible ``invoke(question)`` method.

When an answer generator is supplied, it should match Monica's
``generate_answer(question, documents, llm)`` interface. Without one, the graph
returns retrieved source excerpts rather than generating factual claims.

The detailed ``FeeCalculationResult`` remains available in graph state as
``fee_result``. Successful/zero-valued calculations are separately adapted to
the UI contract's integer-cent ``Calculation`` DTO in ``response``.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import date
from decimal import Decimal
import re
from typing import Any, Protocol, TypedDict
from uuid import uuid4

from langgraph.graph import END, START, StateGraph

from tools.fee_calculator import (
    FeeCalculationInput,
    FeeCalculationResult,
    STATUS_FEE_CALCULATED,
    calculate_late_fee,
)


_QUESTION_SPLIT = re.compile(r"(?<=[?;])|[\n\r]+")
_CONJUNCTION_SPLIT = re.compile(
    r"\s+and\s+(?=(?:what|when|where|who|how|which|is|are|does|do|can|could|"
    r"would|will|should)\b)",
    re.IGNORECASE,
)
_FEE_TERMS = re.compile(r"\b(?:fee|fees|late|overdue|charge|charges)\b", re.IGNORECASE)
_SOURCE_REFERENCE = re.compile(r"\[(S\d+)\]")
_ALLOWED_ANSWER_STATUSES = {"supported", "needs_clarification"}


class Retriever(Protocol):
    """Minimal contract implemented by LangChain's BaseRetriever."""

    def invoke(self, query: str) -> Sequence[Any]:
        ...


class RetrieverFactory(Protocol):
    """Create a tenant/document-scoped retriever for a single request."""

    def __call__(
        self, tenant_name: str, document_ids: Sequence[str] | None
    ) -> Retriever:
        ...


class AgentState(TypedDict, total=False):
    """Graph state; tenant_name and document_ids must be server-authorized."""

    question: str
    tenant_name: str
    document_ids: Sequence[str] | None
    scope: Mapping[str, Any] | None
    asOf: str | date | None
    threadId: str | None
    fee_input: FeeCalculationInput | Mapping[str, Any] | None
    question_parts: list[str]
    input_error: str | None
    retrieval_parts: list[dict[str, Any]]
    retrieval_activity: list[dict[str, str]]
    fee_result: FeeCalculationResult | None
    fee_input_error: str | None
    response: dict[str, Any]


AnswerGenerator = Callable[[str, Sequence[Any], Any], Mapping[str, Any]]
FeeCalculator = Callable[[FeeCalculationInput], FeeCalculationResult]


def build_lease_graph(
    *,
    retriever_factory: RetrieverFactory,
    answer_generator: AnswerGenerator | None = None,
    llm: Any = None,
    fee_calculator: FeeCalculator = calculate_late_fee,
):
    """Build and compile the request graph.

    The factory receives a trusted tenant name and an optional list of
    authorized RAG document IDs, and must return an object exposing
    ``invoke(question)``. The optional generator is compatible with
    ``generate_answer(question, documents, llm)``. No LLM is called by default.

    Input state follows the existing assistant request fields
    (``question``, ``scope``, ``asOf``, ``threadId``) and adds server-only
    ``tenant_name``, ``document_ids``, and optional ``fee_input``. This module
    does not authenticate users, map SQLite lease IDs to RAG document IDs, or
    authorize a scope; those remain the backend caller's responsibility.
    """

    def prepare(state: AgentState) -> dict[str, Any]:
        question = state.get("question")
        if not isinstance(question, str) or not question.strip():
            return {"question_parts": [], "input_error": "A question is required."}
        if len(question) > 2000:
            return {
                "question_parts": [],
                "input_error": "Question must be at most 2000 characters.",
            }
        parts = split_question(question)
        if not parts:
            return {"question_parts": [], "input_error": "A question is required."}
        return {"question_parts": parts, "input_error": None}

    def retrieve(state: AgentState) -> dict[str, Any]:
        parts = state.get("question_parts", [])
        scope = state.get("scope")
        if isinstance(scope, Mapping) and scope.get("type") == "portfolio":
            reason = "Portfolio retrieval is not supported by the tenant-scoped retriever."
            return {
                "retrieval_parts": [
                    {"question": part, "documents": [], "error": reason} for part in parts
                ],
                "retrieval_activity": [
                    {"label": reason, "status": "attention"}
                ],
            }

        tenant_name = state.get("tenant_name")
        document_ids = state.get("document_ids")
        if not isinstance(tenant_name, str) or not tenant_name.strip():
            reason = "Trusted tenant identity is missing; lease retrieval was skipped."
            return {
                "retrieval_parts": [
                    {"question": part, "documents": [], "error": reason} for part in parts
                ],
                "retrieval_activity": [
                    {"label": reason, "status": "attention"}
                ],
            }
        if document_ids is not None and (
            isinstance(document_ids, (str, bytes))
            or not isinstance(document_ids, Sequence)
            or any(not isinstance(item, str) or not item.strip() for item in document_ids)
        ):
            reason = "Authorized document IDs must be a sequence of nonempty strings."
            return {
                "retrieval_parts": [
                    {"question": part, "documents": [], "error": reason} for part in parts
                ],
                "retrieval_activity": [
                    {"label": reason, "status": "attention"}
                ],
            }

        retrieved: list[dict[str, Any]] = []
        activity: list[dict[str, str]] = []
        for part in parts:
            try:
                retriever = retriever_factory(tenant_name, document_ids)
                documents = retriever.invoke(part)
                if not isinstance(documents, Sequence) or isinstance(
                    documents, (str, bytes)
                ):
                    raise TypeError("Retriever must return a sequence of documents.")
                docs = list(documents)
                retrieved.append({"question": part, "documents": docs, "error": None})
                activity.append(
                    {
                        "label": f"Retrieved {len(docs)} evidence item(s) for a question part.",
                        "status": "complete" if docs else "attention",
                    }
                )
            except Exception:
                reason = "Lease evidence could not be retrieved; the graph will abstain."
                retrieved.append({"question": part, "documents": [], "error": reason})
                activity.append({"label": reason, "status": "attention"})
        return {"retrieval_parts": retrieved, "retrieval_activity": activity}

    def calculate_fee(state: AgentState) -> dict[str, Any]:
        fee_questions = [
            part
            for part in state.get("question_parts", [])
            if _FEE_TERMS.search(part)
        ]
        if not fee_questions:
            return {"fee_result": None, "fee_input_error": None}

        supplied = state.get("fee_input")
        if supplied is None:
            return {
                "fee_result": None,
                "fee_input_error": (
                    "Provide monthly rent, due date, payment date, and an explicit "
                    "contractual fee term to calculate a late fee."
                ),
            }
        try:
            if isinstance(supplied, FeeCalculationInput):
                fee_input = supplied
            elif isinstance(supplied, Mapping):
                fee_input = FeeCalculationInput(**dict(supplied))
            else:
                raise TypeError("fee_input must be FeeCalculationInput or a mapping.")
            result = fee_calculator(fee_input)
            if not isinstance(result, FeeCalculationResult):
                raise TypeError("Fee calculator must return FeeCalculationResult.")
        except (TypeError, ValueError) as error:
            return {
                "fee_result": None,
                "fee_input_error": f"Fee calculation inputs need clarification: {error}",
            }
        return {"fee_result": result, "fee_input_error": None}

    def respond(state: AgentState) -> dict[str, Any]:
        if state.get("input_error"):
            return {
                "response": _answer_dto(
                    answer=state["input_error"],
                    status="needs_clarification",
                    citations=[],
                    calculations=[],
                    activity=[{"label": "Request validation failed.", "status": "attention"}],
                    thread_id=state.get("threadId"),
                )
            }

        citations: list[dict[str, Any]] = []
        citation_ids: dict[tuple[str, str], str] = {}
        part_answers: list[str] = []
        part_statuses: list[str] = []
        retrieval_parts = state.get("retrieval_parts", [])

        for item in retrieval_parts:
            question = item["question"]
            documents = item["documents"]
            if documents:
                if answer_generator is None:
                    part_answer, used_citations = _evidence_only_answer(
                        documents, citations, citation_ids
                    )
                else:
                    part_answer, used_citations = _generated_answer(
                        question,
                        documents,
                        answer_generator,
                        llm,
                        citations,
                        citation_ids,
                    )
                if part_answer is None:
                    part_answers.append(
                        f"I can’t safely answer “{question}” because the response "
                        "could not be matched to retrieved citations."
                    )
                    part_statuses.append("needs_clarification")
                else:
                    part_answers.append(part_answer)
                    part_statuses.append("supported")
            else:
                retrieval_error = item.get("error")
                if retrieval_error:
                    part_answers.append(retrieval_error)
                else:
                    part_answers.append(
                        f"I can’t answer “{question}” from the lease evidence available."
                    )
                part_statuses.append("needs_clarification")

        fee_result = state.get("fee_result")
        fee_input_error = state.get("fee_input_error")
        fee_questions = [
            part for part in state.get("question_parts", []) if _FEE_TERMS.search(part)
        ]
        calculations: list[dict[str, Any]] = []
        if fee_result is not None:
            ui_calculation = _fee_calculation_dto(fee_result)
            if ui_calculation is not None:
                calculations.append(ui_calculation)
            if fee_result.status == STATUS_FEE_CALCULATED:
                fee_text = _fee_summary(fee_result)
                _append_to_fee_parts(
                    state.get("question_parts", []), part_answers, fee_text
                )
                part_statuses = [
                    "supported" if _FEE_TERMS.search(part) else current
                    for part, current in zip(
                        state.get("question_parts", []), part_statuses
                    )
                ]
            else:
                _append_to_fee_parts(
                    state.get("question_parts", []),
                    part_answers,
                    fee_result.explanation,
                )
                part_statuses = [
                    "needs_clarification"
                    if _FEE_TERMS.search(part)
                    else current
                    for part, current in zip(
                        state.get("question_parts", []), part_statuses
                    )
                ]
        elif fee_input_error and fee_questions:
            _append_to_fee_parts(
                state.get("question_parts", []), part_answers, fee_input_error
            )
            part_statuses = [
                "needs_clarification" if _FEE_TERMS.search(part) else current
                for part, current in zip(
                    state.get("question_parts", []), part_statuses
                )
            ]

        activity = list(state.get("retrieval_activity", []))
        if fee_result is not None:
            activity.append(
                {
                    "label": "Deterministic fee calculator completed.",
                    "status": (
                        "complete"
                        if fee_result.status == STATUS_FEE_CALCULATED
                        else "attention"
                    ),
                }
            )
        elif fee_input_error and fee_questions:
            activity.append({"label": fee_input_error, "status": "attention"})

        status = (
            "supported"
            if part_statuses and all(x == "supported" for x in part_statuses)
            else "needs_clarification"
        )
        return {
            "response": _answer_dto(
                answer="\n\n".join(part_answers),
                status=status,
                citations=citations,
                calculations=calculations,
                activity=activity,
                thread_id=state.get("threadId"),
            )
        }

    builder = StateGraph(AgentState)
    builder.add_node("prepare", prepare)
    builder.add_node("retrieve", retrieve)
    builder.add_node("calculate_fee", calculate_fee)
    builder.add_node("respond", respond)
    builder.add_edge(START, "prepare")
    builder.add_edge("prepare", "retrieve")
    builder.add_edge("retrieve", "calculate_fee")
    builder.add_edge("calculate_fee", "respond")
    builder.add_edge("respond", END)
    return builder.compile()


def split_question(question: str) -> list[str]:
    """Split obvious multi-part questions without splitting ordinary phrases."""

    parts: list[str] = []
    for segment in _QUESTION_SPLIT.split(question.strip()):
        for part in _CONJUNCTION_SPLIT.split(segment):
            cleaned = part.strip(" \t\r\n,")
            if cleaned:
                parts.append(cleaned)
    return parts


def _evidence_only_answer(
    documents: Sequence[Any],
    citations: list[dict[str, Any]],
    citation_ids: dict[tuple[str, str], str],
) -> tuple[str | None, list[str]]:
    excerpts: list[str] = []
    used: list[str] = []
    for document in documents:
        citation = _citation_for_document(document, "S1")
        if citation is None:
            continue
        citation_id = _register_citation(
            document, citation, citations, citation_ids
        )
        if citation_id not in used:
            used.append(citation_id)
            excerpts.append(f"“{citation['quote']}” [{citation_id}]")
    if not excerpts:
        return None, []
    return "Relevant lease evidence:\n" + "\n".join(excerpts), used


def _generated_answer(
    question: str,
    documents: Sequence[Any],
    answer_generator: AnswerGenerator,
    llm: Any,
    citations: list[dict[str, Any]],
    citation_ids: dict[tuple[str, str], str],
) -> tuple[str | None, list[str]]:
    try:
        generated = answer_generator(question, documents, llm)
    except Exception:
        return None, []
    if not isinstance(generated, Mapping):
        return None, []
    answer = generated.get("answer")
    raw_citations = generated.get("citations")
    if not isinstance(answer, str) or not answer.strip() or not isinstance(
        raw_citations, list
    ):
        return None, []

    local_source_ids: list[str] = []
    for citation in raw_citations:
        source_id = (
            citation.get("source_id")
            if isinstance(citation, Mapping)
            else citation
        )
        if (
            not isinstance(source_id, str)
            or not re.fullmatch(r"S\d+", source_id)
            or source_id in local_source_ids
        ):
            return None, []
        local_source_ids.append(source_id)

    inline_ids = set(_SOURCE_REFERENCE.findall(answer))
    if not local_source_ids or inline_ids != set(local_source_ids):
        return None, []

    local_to_global: dict[str, str] = {}
    for source_id in local_source_ids:
        index = int(source_id[1:]) - 1
        if index < 0 or index >= len(documents):
            return None, []
        document = documents[index]
        citation = _citation_for_document(document, source_id)
        if citation is None:
            return None, []
        global_id = _register_citation(document, citation, citations, citation_ids)
        local_to_global[source_id] = global_id

    for local_id, global_id in local_to_global.items():
        answer = answer.replace(f"[{local_id}]", f"[{global_id}]")
    return answer, list(dict.fromkeys(local_to_global.values()))


def _citation_for_document(document: Any, source_id: str) -> dict[str, Any] | None:
    metadata = getattr(document, "metadata", None)
    if not isinstance(metadata, Mapping):
        return None
    document_id = metadata.get("document_id")
    if not isinstance(document_id, str) or not document_id.strip():
        return None

    quote = metadata.get("quote")
    if not isinstance(quote, str) or not quote.strip():
        spans = metadata.get("source_spans")
        if isinstance(spans, Sequence) and not isinstance(spans, (str, bytes)):
            span_text = [
                span.get("text")
                for span in spans
                if isinstance(span, Mapping)
                and isinstance(span.get("text"), str)
                and span["text"].strip()
            ]
            quote = "\n".join(span_text)
    if not isinstance(quote, str) or not quote.strip():
        page_content = getattr(document, "page_content", None)
        quote = page_content if isinstance(page_content, str) else ""
    if not quote.strip():
        return None

    page = metadata.get("page")
    if not isinstance(page, int) or isinstance(page, bool):
        page = _first_page(metadata)
    citation: dict[str, Any] = {
        "id": source_id,
        "title": _first_text(
            metadata.get("document_title"),
            metadata.get("section_title"),
            metadata.get("source_filename"),
        )
        or "Lease evidence",
        "section": _first_text(
            metadata.get("clause_id"),
            metadata.get("section_id"),
            metadata.get("section"),
            metadata.get("section_title"),
        )
        or "",
        "page": page,
        "quote": quote.strip(),
        "documentId": document_id,
    }
    effective_from = metadata.get("effective_from", metadata.get("effectiveFrom"))
    effective_to = metadata.get("effective_to", metadata.get("effectiveTo"))
    if isinstance(effective_from, str):
        citation["effectiveFrom"] = effective_from
    if isinstance(effective_to, str) or effective_to is None:
        if "effective_to" in metadata or "effectiveTo" in metadata:
            citation["effectiveTo"] = effective_to
    return citation


def _first_page(metadata: Mapping[str, Any]) -> int | None:
    pages = metadata.get("page_numbers")
    if isinstance(pages, Sequence) and not isinstance(pages, (str, bytes)):
        for page in pages:
            if isinstance(page, int) and not isinstance(page, bool):
                return page
    spans = metadata.get("source_spans")
    if isinstance(spans, Sequence) and not isinstance(spans, (str, bytes)):
        for span in spans:
            if isinstance(span, Mapping):
                page = span.get("page_number")
                if isinstance(page, int) and not isinstance(page, bool):
                    return page
    return None


def _first_text(*values: Any) -> str | None:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _register_citation(
    document: Any,
    citation: dict[str, Any],
    citations: list[dict[str, Any]],
    citation_ids: dict[tuple[str, str], str],
) -> str:
    metadata = getattr(document, "metadata", {})
    chunk_id = metadata.get("chunk_id") if isinstance(metadata, Mapping) else None
    identity = (
        str(citation["documentId"]),
        str(chunk_id or f"{citation['section']}:{citation['page']}:{citation['quote']}"),
    )
    existing = citation_ids.get(identity)
    if existing is not None:
        return existing

    global_id = f"S{len(citations) + 1}"
    output = dict(citation)
    output["id"] = global_id
    citations.append(output)
    citation_ids[identity] = global_id
    return global_id


def _fee_summary(result: FeeCalculationResult) -> str:
    fee = result.calculated_late_fee
    maximum = result.statutory_maximum
    if fee is None:
        return result.explanation
    summary = f"Deterministic late-fee calculation: USD {fee:.2f}."
    if maximum is not None:
        summary += f" Statutory maximum: USD {maximum:.2f}."
    return summary


def _fee_calculation_dto(result: FeeCalculationResult) -> dict[str, Any] | None:
    """Adapt the calculator result to the UI contract's integer-cent DTO."""

    if result.calculated_late_fee is None:
        return None

    detail = result.to_dict()
    input_values = {
        key: value
        for key, value in detail["inputs"].items()
        if isinstance(value, (int, str, bool))
    }
    input_values["calculation_status"] = detail["status"]
    input_values["formula"] = detail["formula"]
    input_values["explanation"] = detail["explanation"]
    if detail["statutory_maximum"] is not None:
        input_values["statutory_maximum_usd"] = detail["statutory_maximum"]

    cents = int(
        (result.calculated_late_fee * Decimal("100")).to_integral_exact()
    )
    return {
        "label": "North Carolina monthly rent late fee",
        "inputs": input_values,
        "result": cents,
        "currency": "USD",
        "method": (
            "N.C. General Statute §42-46 monthly rent late-fee calculation; "
            "result is integer cents."
        ),
    }


def _append_to_fee_parts(
    question_parts: Sequence[str], answers: list[str], text: str
) -> None:
    for index, question in enumerate(question_parts):
        if index < len(answers) and _FEE_TERMS.search(question):
            answers[index] = f"{answers[index]}\n{text}" if answers[index] else text


def _answer_dto(
    *,
    answer: str,
    status: str,
    citations: list[dict[str, Any]],
    calculations: list[dict[str, Any]],
    activity: list[dict[str, str]],
    thread_id: str | None,
) -> dict[str, Any]:
    safe_status = status if status in _ALLOWED_ANSWER_STATUSES else "needs_clarification"
    return {
        "id": str(uuid4()),
        "threadId": thread_id if isinstance(thread_id, str) and thread_id else str(uuid4()),
        "answer": answer,
        "status": safe_status,
        "citations": citations,
        "calculations": calculations,
        "activity": activity,
        "compliance": {"status": "unavailable"},
    }

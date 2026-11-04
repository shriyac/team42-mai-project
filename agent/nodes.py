"""LangGraph node functions and mock-compatible lease retrieval."""

from __future__ import annotations

from calendar import monthrange
from collections.abc import Callable, Mapping, Sequence
from datetime import date, datetime
from decimal import Decimal
import re
import unicodedata
from typing import Any, Protocol

from tools.fee_calculator import (
    FeeCalculationInput,
    FeeCalculationResult,
    STATUS_CLARIFICATION_REQUIRED,
    STATUS_INVALID_INPUT,
    calculate_late_fee,
)

from .prompts import ABSTENTION, format_evidence_answer
from .state import LAGAState


class Retriever(Protocol):
    """The LangChain retriever interface used by Monica's implementation."""

    def invoke(self, query: str) -> Sequence[Any]:
        ...


class RetrieverFactory(Protocol):
    """Create a retriever already scoped to the authorized tenant and lease."""

    def __call__(
        self, tenant_id: str, tenant_name: str, lease_id: str
    ) -> Retriever:
        ...


AnswerGenerator = Callable[[str, Sequence[Any], Any], Mapping[str, Any]]
FeeCalculator = Callable[[FeeCalculationInput], FeeCalculationResult]


_FEE_INTENT = re.compile(
    r"\b(?:late\s+fees?|late\s+charges?|overdue\s+fees?|overdue\s+charges?)\b",
    re.IGNORECASE,
)
_QUESTION_SPLIT = re.compile(r"(?<=[?;])|[\n\r]+")
_CONJUNCTION_SPLIT = re.compile(
    r"\s+and\s+(?=(?:what|when|where|who|how|which|is|are|does|do|can|could|"
    r"would|will|should)\b)",
    re.IGNORECASE,
)
_MONEY = r"(?:\$?\s*)?(\d[\d,]*(?:\.\d{1,2})?)"
_MONTHLY_RENT_PATTERNS = (
    re.compile(
        rf"\bmonthly\s+(?:base\s+)?rent(?:\s+(?:is|of))?\s*[:=]?\s*{_MONEY}",
        re.IGNORECASE,
    ),
    re.compile(
        rf"\brent\s+(?:is|of)\s*{_MONEY}\s*(?:per\s+month|monthly)\b",
        re.IGNORECASE,
    ),
)
_FLAT_FEE = re.compile(
    rf"\b(?:flat\s+)?late\s+(?:fee|charge)\s+(?:of|is|=)\s*{_MONEY}",
    re.IGNORECASE,
)
_PERCENT_FEE = re.compile(
    r"\b(?:late\s+fee|late\s+charge)\s+(?:of|is|=)\s*(\d+(?:\.\d+)?)\s*%",
    re.IGNORECASE,
)
_DUE_DAY = re.compile(
    r"\b(?:due|payable)\s+(?:on|by)\s+"
    r"(first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|"
    r"eleventh|twelfth|thirteenth|fourteenth|fifteenth|sixteenth|seventeenth|"
    r"eighteenth|nineteenth|twentieth|twenty[- ]first|twenty[- ]second|"
    r"twenty[- ]third|twenty[- ]fourth|twenty[- ]fifth|twenty[- ]sixth|"
    r"twenty[- ]seventh|twenty[- ]eighth|twenty[- ]ninth|thirtieth|"
    r"thirty[- ]first|\d{1,2}(?:st|nd|rd|th)?)"
    r"(?:\s+day)?\s+(?:of\s+)?(?:each|every)\s+month\b",
    re.IGNORECASE,
)
_DATE_TOKEN = (
    r"(?:\d{4}-\d{2}-\d{2}|"
    r"\d{1,2}/\d{1,2}/\d{4}|"
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|"
    r"Dec(?:ember)?)\s+\d{1,2},?\s+\d{4})"
)
_PAYMENT_DATE = re.compile(
    rf"\b(?:paid|payment(?:\s+was)?\s+made|payment\s+date)"
    rf"\s*(?:on|is|:)?\s*({_DATE_TOKEN})",
    re.IGNORECASE,
)
_EXPLICIT_DUE_DATE = re.compile(
    rf"\b(?:rent\s+)?due\s+date\s*[:=]?\s*({_DATE_TOKEN})",
    re.IGNORECASE,
)
_NO_FEE_CHARGED = re.compile(
    r"\b(?:no\s+(?:late\s+)?(?:fee|charge)\s+(?:has\s+been\s+)?"
    r"(?:charged|assessed|paid)|"
    r"(?:have|has)\s+not\s+(?:been\s+)?(?:charged|assessed|paid)"
    r"(?:\s+(?:a\s+)?(?:late\s+)?(?:fee|charge))?)\b",
    re.IGNORECASE,
)
_FEE_CHARGED = re.compile(
    r"\b(?:already|previously)\s+(?:been\s+)?(?:charged|assessed|paid)\b",
    re.IGNORECASE,
)

_ORDINAL_DAYS = {
    word: index
    for index, word in enumerate(
        [
            "",
            "first",
            "second",
            "third",
            "fourth",
            "fifth",
            "sixth",
            "seventh",
            "eighth",
            "ninth",
            "tenth",
            "eleventh",
            "twelfth",
            "thirteenth",
            "fourteenth",
            "fifteenth",
            "sixteenth",
            "seventeenth",
            "eighteenth",
            "nineteenth",
            "twentieth",
        ]
    )
}
_ORDINAL_DAYS.update(
    {
        "twenty-first": 21,
        "twenty first": 21,
        "twenty-second": 22,
        "twenty second": 22,
        "twenty-third": 23,
        "twenty third": 23,
        "twenty-fourth": 24,
        "twenty fourth": 24,
        "twenty-fifth": 25,
        "twenty fifth": 25,
        "twenty-sixth": 26,
        "twenty sixth": 26,
        "twenty-seventh": 27,
        "twenty seventh": 27,
        "twenty-eighth": 28,
        "twenty eighth": 28,
        "twenty-ninth": 29,
        "twenty ninth": 29,
        "thirtieth": 30,
        "thirty-first": 31,
        "thirty first": 31,
    }
)


class MockLeaseRetriever:
    """Deterministic mock implementing ``invoke(query)``.

    It returns only documents whose metadata identifies the requested lease
    and matches the supplied tenant ID or normalized tenant name. A missing
    ownership field, lease ID, or document ID fails closed.
    """

    def __init__(
        self,
        documents: Sequence[Any],
        *,
        tenant_id: str,
        tenant_name: str,
        lease_id: str,
        results_by_query: Mapping[str, Sequence[Any]] | None = None,
        query_observer: Callable[[str], None] | None = None,
    ):
        self.documents = list(documents)
        self.tenant_id = tenant_id
        self.tenant_name = tenant_name
        self.lease_id = lease_id
        self.results_by_query = dict(results_by_query or {})
        self.query_observer = query_observer

    def invoke(self, query: str) -> list[Any]:
        if self.query_observer:
            self.query_observer(query)
        candidates = self.results_by_query.get(query, self.documents)
        return [
            document
            for document in candidates
            if is_authorized_lease_document(
                document,
                tenant_id=self.tenant_id,
                tenant_name=self.tenant_name,
                lease_id=self.lease_id,
            )
        ]


class MockLeaseRetrieverFactory:
    """Factory used by tests and safe local runs with no RAG integration."""

    def __init__(
        self,
        documents: Sequence[Any] = (),
        *,
        results_by_query: Mapping[str, Sequence[Any]] | None = None,
    ):
        self.documents = list(documents)
        self.results_by_query = dict(results_by_query or {})
        self.calls: list[tuple[str, str, str]] = []
        self.queries: list[str] = []

    def __call__(self, tenant_id: str, tenant_name: str, lease_id: str) -> MockLeaseRetriever:
        self.calls.append((tenant_id, tenant_name, lease_id))
        return MockLeaseRetriever(
            self.documents,
            tenant_id=tenant_id,
            tenant_name=tenant_name,
            lease_id=lease_id,
            results_by_query=self.results_by_query,
            query_observer=self.queries.append,
        )


def split_question(question: str) -> list[str]:
    """Split straightforward multi-part questions for separate retrieval."""

    parts: list[str] = []
    for segment in _QUESTION_SPLIT.split(question.strip()):
        for part in _CONJUNCTION_SPLIT.split(segment):
            clean = part.strip(" \t\r\n,")
            if clean:
                parts.append(clean)
    return parts


def is_fee_question(question: str) -> bool:
    return bool(_FEE_INTENT.search(question))


def is_authorized_lease_document(
    document: Any, *, tenant_id: str, tenant_name: str, lease_id: str
) -> bool:
    metadata = getattr(document, "metadata", None)
    if not isinstance(metadata, Mapping):
        return False
    if metadata.get("lease_id") != lease_id:
        return False
    if not isinstance(metadata.get("document_id"), str) or not metadata["document_id"].strip():
        return False
    if metadata.get("access") == "shared":
        return False

    has_owner = False
    if "tenant_id" in metadata:
        has_owner = True
        if metadata.get("tenant_id") != tenant_id:
            return False
    if "tenant_name" in metadata:
        has_owner = True
        if _tenant_key(metadata.get("tenant_name")) != _tenant_key(tenant_name):
            return False
    return has_owner


def plan_query(state: LAGAState) -> dict[str, Any]:
    question = state.get("question")
    errors = list(state.get("validation_errors", []))
    if not isinstance(question, str) or not question.strip():
        errors.append("A tenant question is required.")
        parts: list[str] = []
    elif len(question) > 2000:
        errors.append("The tenant question must be at most 2000 characters.")
        parts = []
    else:
        parts = split_question(question)
        if not parts:
            errors.append("A tenant question is required.")

    for field in ("tenant_id", "tenant_name", "lease_id"):
        value = state.get(field)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"Trusted {field} is required.")

    as_of = state.get("as_of")
    if isinstance(as_of, str):
        try:
            date.fromisoformat(as_of)
        except ValueError:
            errors.append("as_of must be an ISO calendar date.")
    elif not isinstance(as_of, date):
        errors.append("as_of must be an ISO calendar date.")

    return {
        "subquestions": parts,
        "fee_required": any(is_fee_question(part) for part in parts),
        "validation_errors": errors,
        "validation_status": "pending",
        "retry_count": int(state.get("retry_count", 0)),
        "retrieved_evidence": [],
        "calculations": [],
        "citations": [],
        "tool_activity": list(state.get("tool_activity", [])),
    }


def retrieve_context(
    state: LAGAState, retriever_factory: RetrieverFactory
) -> dict[str, Any]:
    if state.get("validation_errors"):
        return {"retrieved_evidence": [], "citations": []}

    tenant_id = state["tenant_id"]
    tenant_name = state["tenant_name"]
    lease_id = state["lease_id"]
    previous = {
        item["subquestion"]: list(item.get("documents", []))
        for item in state.get("retrieved_evidence", [])
    }
    evidence: list[dict[str, Any]] = []
    activity = list(state.get("tool_activity", []))
    retry_queries = state.get("retry_queries", {})

    for subquestion in state.get("subquestions", []):
        query = retry_queries.get(subquestion, subquestion)
        try:
            retriever = retriever_factory(tenant_id, tenant_name, lease_id)
            raw_documents = retriever.invoke(query)
            if not isinstance(raw_documents, Sequence) or isinstance(
                raw_documents, (str, bytes)
            ):
                raise TypeError("Retriever.invoke must return a sequence of documents.")
            new_documents = [
                document
                for document in raw_documents
                if is_authorized_lease_document(
                    document,
                    tenant_id=tenant_id,
                    tenant_name=tenant_name,
                    lease_id=lease_id,
                )
            ]
            documents = _merge_documents(previous.get(subquestion, []), new_documents)
            evidence.append(
                {
                    "subquestion": subquestion,
                    "query": query,
                    "documents": documents,
                }
            )
            activity.append(
                {
                    "label": (
                        f"Retrieved {len(new_documents)} authorized evidence item(s) "
                        f"for {subquestion!r}."
                    ),
                    "status": "complete" if documents else "attention",
                }
            )
        except Exception:
            evidence.append(
                {"subquestion": subquestion, "query": query, "documents": []}
            )
            activity.append(
                {
                    "label": f"Retrieval failed for {subquestion!r}; evidence was withheld.",
                    "status": "attention",
                }
            )
    return {"retrieved_evidence": evidence, "tool_activity": activity}


def execute_tools(
    state: LAGAState, fee_calculator: FeeCalculator = calculate_late_fee
) -> dict[str, Any]:
    if not state.get("fee_required"):
        return {"calculation": None, "calculations": []}

    fee_input, extraction_errors = extract_fee_input(state)
    if fee_input is None:
        errors = list(state.get("validation_errors", []))
        errors.extend(extraction_errors)
        activity = list(state.get("tool_activity", []))
        activity.append(
            {
                "label": "Fee calculation needs explicit lease or payment details.",
                "status": "attention",
            }
        )
        return {
            "calculation": None,
            "calculations": [],
            "validation_errors": errors,
            "tool_activity": activity,
        }

    result = fee_calculator(fee_input)
    if not isinstance(result, FeeCalculationResult):
        raise TypeError("fee_calculator must return FeeCalculationResult.")
    errors = list(state.get("validation_errors", []))
    if result.status in {STATUS_CLARIFICATION_REQUIRED, STATUS_INVALID_INPUT}:
        errors.extend(result.validation_errors or (result.explanation,))
    activity = list(state.get("tool_activity", []))
    activity.append(
        {
            "label": "Deterministic fee calculator invoked.",
            "status": (
                "attention"
                if result.status in {STATUS_CLARIFICATION_REQUIRED, STATUS_INVALID_INPUT}
                else "complete"
            ),
        }
    )
    return {
        "calculation": result,
        "calculations": [result.to_dict()],
        "validation_errors": errors,
        "tool_activity": activity,
    }


def extract_fee_input(
    state: LAGAState,
) -> tuple[FeeCalculationInput | None, list[str]]:
    """Extract only explicit, unambiguous fee facts; do not fill missing terms."""

    evidence_text = _evidence_text(state.get("retrieved_evidence", []))
    question = state.get("question", "")
    combined = f"{question}\n{evidence_text}"
    errors: list[str] = []

    rent_values = _unique_decimal_matches(
        evidence_text, _MONTHLY_RENT_PATTERNS, "monthly rent", errors
    )
    if len(rent_values) != 1:
        errors.append("A single explicit monthly rent amount is required.")

    payment_date = _payment_date(question)
    if payment_date is None:
        errors.append("An explicit payment date is required for fee calculation.")

    due_date = _due_date(evidence_text, payment_date, errors)

    fee_already_charged = _charged_state(combined)
    if fee_already_charged is None:
        errors.append(
            "Clarify whether a late fee has already been charged for this installment."
        )

    flat_values = _unique_decimal_matches(
        evidence_text, (_FLAT_FEE,), "contractual flat fee", errors
    )
    percentage_values = _unique_decimal_matches(
        evidence_text, (_PERCENT_FEE,), "contractual fee percentage", errors
    )
    if len(flat_values) > 1 or len(percentage_values) > 1:
        errors.append("The lease contains conflicting contractual late-fee terms.")

    if (
        len(rent_values) != 1
        or payment_date is None
        or due_date is None
        or fee_already_charged is None
        or len(flat_values) > 1
        or len(percentage_values) > 1
    ):
        return None, list(dict.fromkeys(errors))

    return (
        FeeCalculationInput(
            monthly_rent=rent_values[0],
            due_date=due_date,
            payment_date=payment_date,
            contractual_fee_amount=flat_values[0] if flat_values else None,
            contractual_fee_percentage=(
                percentage_values[0] if percentage_values else None
            ),
            fee_already_charged=fee_already_charged,
        ),
        errors,
    )


def generate_answer(
    state: LAGAState,
    answer_generator: AnswerGenerator | None = None,
    llm: Any = None,
) -> dict[str, Any]:
    evidence_bundles = state.get("retrieved_evidence", [])
    all_citations: list[dict[str, Any]] = []
    answer_parts: list[dict[str, Any]] = []
    next_source_number = 1
    activity = list(state.get("tool_activity", []))

    for bundle in evidence_bundles:
        subquestion = bundle["subquestion"]
        documents = bundle.get("documents", [])
        if not documents:
            answer_parts.append(
                {
                    "subquestion": subquestion,
                    "answer": "",
                    "source_ids": [],
                    "error": "No authorized evidence was retrieved.",
                }
            )
            continue

        if answer_generator is None:
            excerpts: list[tuple[str, str]] = []
            source_ids: list[str] = []
            for document in documents:
                source_id = f"S{next_source_number}"
                citation = citation_from_document(document, source_id)
                if citation is None:
                    continue
                next_source_number += 1
                all_citations.append(citation)
                source_ids.append(source_id)
                excerpts.append((source_id, citation["source_text"]))
            answer = format_evidence_answer(subquestion, excerpts)
            answer_parts.append(
                {
                    "subquestion": subquestion,
                    "answer": answer,
                    "source_ids": source_ids,
                    "error": "" if answer else "Evidence lacked citation metadata.",
                }
            )
            continue

        try:
            generated = answer_generator(subquestion, documents, llm)
        except Exception:
            generated = None
        answer = generated.get("answer") if isinstance(generated, Mapping) else None
        raw_citations = (
            generated.get("citations") if isinstance(generated, Mapping) else None
        )
        if not isinstance(answer, str):
            answer = ""
        source_ids = []
        error = ""
        if not isinstance(raw_citations, list):
            error = "Answer generator returned no citation list."
            raw_citations = []

        local_to_global: dict[str, str] = {}
        for citation_item in raw_citations:
            local_id = (
                citation_item.get("source_id")
                if isinstance(citation_item, Mapping)
                else citation_item
            )
            if (
                not isinstance(local_id, str)
                or not re.fullmatch(r"S\d+", local_id)
                or local_id in local_to_global
            ):
                error = "Answer generator returned an invalid source ID."
                continue
            document_index = int(local_id[1:]) - 1
            if not 0 <= document_index < len(documents):
                error = "Answer generator cited evidence that was not retrieved."
                continue
            global_id = f"S{next_source_number}"
            citation = citation_from_document(documents[document_index], global_id)
            if citation is None:
                error = "Cited evidence lacks required source metadata."
                continue
            next_source_number += 1
            local_to_global[local_id] = global_id
            source_ids.append(global_id)
            all_citations.append(citation)

        for local_id, global_id in local_to_global.items():
            answer = answer.replace(f"[{local_id}]", f"[{global_id}]")
        answer_parts.append(
            {
                "subquestion": subquestion,
                "answer": answer,
                "source_ids": source_ids,
                "error": error,
            }
        )

    calculation = state.get("calculation")
    if calculation is not None:
        fee_text = calculation.explanation
        for part in answer_parts:
            if is_fee_question(part["subquestion"]):
                part["answer"] = (
                    f"{part['answer']} {fee_text}".strip()
                    if part["answer"]
                    else fee_text
                )
                if calculation.status not in {
                    STATUS_CLARIFICATION_REQUIRED,
                    STATUS_INVALID_INPUT,
                }:
                    continue
                part["error"] = (
                    part.get("error", "")
                    or "Fee calculation requires contractual clarification."
                )

    activity.append(
        {
            "label": "Answer assembled from retrieved evidence and deterministic tools.",
            "status": "complete",
        }
    )
    return {
        "answer_parts": answer_parts,
        "citations": all_citations,
        "answer": "\n\n".join(
            part["answer"] for part in answer_parts if part["answer"]
        ),
        "tool_activity": activity,
    }


def validate_answer(state: LAGAState) -> dict[str, Any]:
    errors = list(state.get("validation_errors", []))
    citation_ids = {
        citation.get("source_id")
        for citation in state.get("citations", [])
        if isinstance(citation, Mapping)
    }
    retry_subquestions: list[str] = []
    bundles = {
        item["subquestion"]: item
        for item in state.get("retrieved_evidence", [])
    }

    for part in state.get("answer_parts", []):
        subquestion = part["subquestion"]
        answer = part.get("answer", "")
        source_ids = set(part.get("source_ids", []))
        inline_ids = set(re.findall(r"\[(S\d+)\]", answer))
        bundle = bundles.get(subquestion, {})
        if not bundle.get("documents"):
            errors.append(f"No evidence supports subquestion: {subquestion}")
            retry_subquestions.append(subquestion)
        if part.get("error"):
            errors.append(part["error"])
            retry_subquestions.append(subquestion)
        if not answer.strip() or not source_ids or inline_ids != source_ids:
            errors.append(f"Answer citations do not validate for: {subquestion}")
            retry_subquestions.append(subquestion)
        if not source_ids <= citation_ids:
            errors.append(f"Answer cited a source outside retrieved evidence: {subquestion}")
            retry_subquestions.append(subquestion)

    calculation = state.get("calculation")
    if state.get("fee_required"):
        if calculation is None:
            errors.append("Late-fee inputs could not be safely extracted.")
            retry_subquestions.extend(
                part for part in state.get("subquestions", []) if is_fee_question(part)
            )
        else:
            if state.get("calculations") != [calculation.to_dict()]:
                errors.append("Fee output did not originate from the deterministic calculator.")
                retry_subquestions.extend(
                    part for part in state.get("subquestions", []) if is_fee_question(part)
                )
            if calculation.status in {
                STATUS_CLARIFICATION_REQUIRED,
                STATUS_INVALID_INPUT,
            }:
                errors.extend(calculation.validation_errors or (calculation.explanation,))
                retry_subquestions.extend(
                    part for part in state.get("subquestions", []) if is_fee_question(part)
                )

    errors = list(dict.fromkeys(error for error in errors if error))
    activity = list(state.get("tool_activity", []))
    activity.append(
        {
            "label": (
                "Answer validation passed."
                if not errors
                else f"Answer validation found {len(errors)} issue(s)."
            ),
            "status": "complete" if not errors else "attention",
        }
    )
    return {
        "validation_status": "passed" if not errors else "failed",
        "validation_errors": errors,
        "retry_subquestions": list(dict.fromkeys(retry_subquestions)),
        "tool_activity": activity,
    }


def prepare_retry(state: LAGAState) -> dict[str, Any]:
    retry_count = int(state.get("retry_count", 0)) + 1
    targets = state.get("retry_subquestions") or state.get("subquestions", [])
    retry_queries = {
        question: (
            "lease agreement exact clause text, applicable conditions, fees, "
            f"dates, and exceptions: {question}"
        )
        for question in targets
    }
    activity = list(state.get("tool_activity", []))
    activity.append(
        {
            "label": "One targeted evidence retry is being used.",
            "status": "attention",
        }
    )
    return {
        "retry_count": retry_count,
        "retry_queries": retry_queries,
        "validation_errors": [],
    }


def safe_abstain(state: LAGAState) -> dict[str, Any]:
    calculation = state.get("calculation")
    if calculation and calculation.status == STATUS_CLARIFICATION_REQUIRED:
        answer = (
            "I can’t calculate a late fee without an unambiguous contractual fee "
            f"term. {calculation.explanation}"
        )
    elif calculation and calculation.status == STATUS_INVALID_INPUT:
        answer = (
            "I can’t calculate a late fee from the available information. "
            + calculation.explanation
        )
    else:
        answer = ABSTENTION
    activity = list(state.get("tool_activity", []))
    activity.append({"label": "Abstained after validation/retrieval.", "status": "attention"})
    return {
        "answer": answer,
        "citations": [],
        "validation_status": "abstained",
        "tool_activity": activity,
    }


def citation_from_document(document: Any, source_id: str) -> dict[str, Any] | None:
    metadata = getattr(document, "metadata", None)
    if not isinstance(metadata, Mapping):
        return None
    document_id = metadata.get("document_id")
    lease_id = metadata.get("lease_id")
    if (
        not isinstance(document_id, str)
        or not document_id.strip()
        or not isinstance(lease_id, str)
        or not lease_id.strip()
    ):
        return None
    source_text = _source_text(document, metadata)
    if not source_text:
        return None
    page_number = metadata.get("page_number", metadata.get("page"))
    if not isinstance(page_number, int) or isinstance(page_number, bool):
        page_number = _first_page(metadata)
    clause_id = metadata.get("clause_id", metadata.get("section_id", ""))
    return {
        "source_id": source_id,
        "document_id": document_id,
        "lease_id": lease_id,
        "page_number": page_number,
        "clause_id": clause_id if isinstance(clause_id, str) else "",
        "source_text": source_text,
        "document_title": str(metadata.get("document_title", "")),
        "document_type": str(metadata.get("document_type", "")),
    }


def _source_text(document: Any, metadata: Mapping[str, Any]) -> str:
    quote = metadata.get("quote")
    if isinstance(quote, str) and quote.strip():
        return quote.strip()
    spans = metadata.get("source_spans")
    if isinstance(spans, Sequence) and not isinstance(spans, (str, bytes)):
        chunks = [
            span["text"].strip()
            for span in spans
            if isinstance(span, Mapping)
            and isinstance(span.get("text"), str)
            and span["text"].strip()
        ]
        if chunks:
            return "\n".join(chunks)
    page_content = getattr(document, "page_content", "")
    return page_content.strip() if isinstance(page_content, str) else ""


def _first_page(metadata: Mapping[str, Any]) -> int | None:
    pages = metadata.get("page_numbers")
    if isinstance(pages, Sequence) and not isinstance(pages, (str, bytes)):
        for page in pages:
            if isinstance(page, int) and not isinstance(page, bool):
                return page
    return None


def _merge_documents(existing: Sequence[Any], incoming: Sequence[Any]) -> list[Any]:
    result: list[Any] = []
    seen: set[tuple[str, str]] = set()
    for document in [*existing, *incoming]:
        metadata = getattr(document, "metadata", {})
        if not isinstance(metadata, Mapping):
            continue
        identity = (
            str(metadata.get("document_id", "")),
            str(metadata.get("chunk_id", metadata.get("clause_id", ""))),
        )
        if identity in seen:
            continue
        seen.add(identity)
        result.append(document)
    return result


def _evidence_text(evidence: Sequence[Mapping[str, Any]]) -> str:
    pieces: list[str] = []
    for bundle in evidence:
        for document in bundle.get("documents", []):
            metadata = getattr(document, "metadata", {})
            if isinstance(metadata, Mapping):
                text = _source_text(document, metadata)
                if text:
                    pieces.append(text)
    return "\n".join(pieces)


def _unique_decimal_matches(
    text: str,
    patterns: Sequence[re.Pattern[str]],
    label: str,
    errors: list[str],
) -> list[Decimal]:
    values: set[Decimal] = set()
    for pattern in patterns:
        for match in pattern.finditer(text):
            raw = match.group(1).replace(",", "")
            try:
                values.add(Decimal(raw))
            except Exception:
                errors.append(f"Could not parse {label} from retrieved evidence.")
    return sorted(values)


def _payment_date(question: str) -> date | None:
    match = _PAYMENT_DATE.search(question)
    return _parse_date_token(match.group(1)) if match else None


def _due_date(
    evidence_text: str, payment_date: date | None, errors: list[str]
) -> date | None:
    explicit_dates = {
        parsed
        for match in _EXPLICIT_DUE_DATE.finditer(evidence_text)
        if (parsed := _parse_date_token(match.group(1))) is not None
    }
    days: set[int] = set()
    for match in _DUE_DAY.finditer(evidence_text):
        raw = match.group(1).lower().replace(" ", "-")
        day = _ORDINAL_DAYS.get(raw)
        if day is None:
            day = int(re.sub(r"(st|nd|rd|th)$", "", raw))
        days.add(day)
    if len(explicit_dates) > 1 or len(days) > 1:
        errors.append("The lease contains conflicting rent due dates.")
        return None
    if explicit_dates:
        due_date = next(iter(explicit_dates))
        if days and due_date.day != next(iter(days)):
            errors.append("The lease's explicit due date conflicts with its due day.")
            return None
        return due_date
    if not days or payment_date is None:
        errors.append("An explicit rent due date or due day is required.")
        return None

    due_day = next(iter(days))
    year, month = payment_date.year, payment_date.month
    if payment_date.day < due_day:
        month -= 1
        if month == 0:
            month, year = 12, year - 1
    if due_day > monthrange(year, month)[1]:
        errors.append("The stated rent due day does not exist in the payment month.")
        return None
    return date(year, month, due_day)


def _parse_date_token(value: str) -> date | None:
    try:
        return date.fromisoformat(value)
    except ValueError:
        pass
    for date_format in ("%m/%d/%Y", "%B %d, %Y", "%B %d %Y", "%b %d, %Y", "%b %d %Y"):
        try:
            return datetime.strptime(value, date_format).date()
        except ValueError:
            continue
    return None


def _charged_state(text: str) -> bool | None:
    if _NO_FEE_CHARGED.search(text):
        return False
    if _FEE_CHARGED.search(text):
        return True
    return None


def _tenant_key(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())

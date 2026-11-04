"""Deterministic LangGraph nodes; no model or service is called by default."""

from collections.abc import Callable, Mapping, Sequence
from datetime import date
import re
from typing import Any

from tools.fee_calculator import (
    FeeCalculationInput, FeeCalculationResult, STATUS_CLARIFICATION_REQUIRED,
    STATUS_INVALID_INPUT, calculate_late_fee,
)

from .evidence import (
    RetrieverFactory, MockLeaseRetrieverFactory, MockLeaseRetriever,
    citation_from_document, is_authorized_lease_document, merge_documents,
    source_text,
)
from .fee_inputs import extract_fee_input
from .prompts import ABSTENTION, format_evidence_answer
from .state import LAGAState


AnswerGenerator = Callable[[str, Sequence[Any], Any], Mapping[str, Any]]
FeeCalculator = Callable[[FeeCalculationInput], FeeCalculationResult]
UNRESOLVED = {STATUS_CLARIFICATION_REQUIRED, STATUS_INVALID_INPUT}
SOURCE_REFERENCE = re.compile(r"\[(S\d+)\]")
FEE_INTENT = re.compile(r"\b(?:late\s+(?:fees?|charges?)|overdue)\b", re.I)


def is_fee_question(question):
    return bool(FEE_INTENT.search(question))


def split_question(question):
    parts = []
    for segment in re.split(r"(?<=[?;])|[\n\r]+", question.strip()):
        for part in re.split(
            r"\s+and\s+(?=(?:what|when|where|who|how|which|is|are|does|do|can|"
            r"could|would|will|should)\b)", segment, flags=re.I,
        ):
            cleaned = part.strip(" \t\r\n,")
            if cleaned:
                parts.append(cleaned)
    return parts


def plan_query(state: LAGAState):
    errors = []
    question = state.get("question")
    if not isinstance(question, str) or not question.strip() or len(question) > 2000:
        errors.append("A nonempty question of at most 2000 characters is required.")
    for field in ("tenant_id", "tenant_name", "lease_id"):
        if not isinstance(state.get(field), str) or not state[field].strip():
            errors.append(f"Trusted {field} is required.")
    try:
        value = state.get("as_of")
        if not isinstance(value, date):
            date.fromisoformat(value)
    except (ValueError, TypeError):
        errors.append("as_of must be an ISO calendar date.")
    parts = split_question(question) if not errors else []
    return {
        "subquestions": parts, "fee_required": any(map(is_fee_question, parts)),
        "input_errors": errors, "validation_errors": errors,
        "validation_status": "pending", "retry_count": 0, "retry_queries": {},
        "retrieved_evidence": [], "calculations": [], "calculation": None,
        "citations": [], "answer_parts": [], "tool_activity": [],
    }


def retrieve_context(state: LAGAState, retriever_factory: RetrieverFactory):
    if state.get("input_errors"):
        return {"retrieved_evidence": []}
    previous = {
        bundle["subquestion"]: bundle.get("documents", [])
        for bundle in state.get("retrieved_evidence", [])
    }
    scope = {key: state[key] for key in ("tenant_id", "tenant_name", "lease_id")}
    bundles, activity = [], list(state.get("tool_activity", []))
    for question in state.get("subquestions", []):
        retry_queries = state.get("retry_queries", {})
        if state.get("retry_count") and question not in retry_queries:
            bundles.append({"subquestion": question, "query": question,
                            "documents": previous.get(question, [])})
            continue
        query = retry_queries.get(question, question)
        error = ""
        try:
            raw = retriever_factory(**scope).invoke(query)
            if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
                raise TypeError("Retriever.invoke must return a document sequence.")
            authorized = [doc for doc in raw if is_authorized_lease_document(doc, **scope)]
            documents = merge_documents(previous.get(question, []), authorized)
        except Exception:
            documents, error = [], "Lease retrieval failed; no evidence was assumed."
        bundles.append({
            "subquestion": question, "query": query, "documents": documents, "error": error,
        })
        activity.append({
            "label": error or f"Retrieved {len(documents)} authorized item(s) for {question!r}.",
            "status": "complete" if documents else "attention",
        })
    return {"retrieved_evidence": bundles, "tool_activity": activity}


def execute_tools(state: LAGAState, fee_calculator: FeeCalculator = calculate_late_fee):
    if not state.get("fee_required") or state.get("input_errors"):
        return {"calculation": None, "calculations": [], "fee_errors": []}
    inputs, errors = extract_fee_input(state)
    result = None
    if inputs is not None:
        try:
            result = fee_calculator(inputs)
            if not isinstance(result, FeeCalculationResult):
                raise TypeError("Calculator did not return FeeCalculationResult.")
        except Exception:
            result = None
            errors.append("The deterministic fee calculator could not complete.")
    activity = list(state.get("tool_activity", []))
    activity.append({
        "label": ("Deterministic fee calculator invoked." if result is not None
                  else "Fee calculation needs explicit lease/payment details."),
        "status": "complete" if result and result.status not in UNRESOLVED else "attention",
    })
    return {
        "calculation": result, "calculations": [result.to_dict()] if result else [],
        "fee_errors": errors, "tool_activity": activity,
    }


def _extractive_claims_only(answer, documents):
    """Fail closed on generated paraphrases without a semantic verifier.

    A valid citation alone does not prove entailment. The default answerer is
    extractive; optional RAG generators must also supply verifiable excerpts.
    """
    evidence = " ".join(source_text(doc) for doc in documents)
    normalize = lambda value: re.sub(r"\W+", " ", value).casefold().strip()
    supported = normalize(evidence)
    claims = SOURCE_REFERENCE.sub("", answer)
    return all(
        normalize(claim) in supported
        for claim in re.split(r"[.!?;\n]+", claims)
        if normalize(claim)
    )


def _generated_part(question, documents, answer_generator, llm, citations):
    try:
        generated = answer_generator(question, documents, llm)
        answer, raw = generated["answer"], generated["citations"]
        if not isinstance(answer, str) or not isinstance(raw, list):
            raise ValueError
        local_ids = [item.get("source_id") if isinstance(item, Mapping) else item for item in raw]
        if (
            not local_ids or any(not isinstance(s, str) or not re.fullmatch(r"S\d+", s)
                                 for s in local_ids)
            or len(set(local_ids)) != len(local_ids)
            or set(SOURCE_REFERENCE.findall(answer)) != set(local_ids)
        ):
            raise ValueError
        mapping, records, cited_documents = {}, [], []
        for source_id in local_ids:
            index = int(source_id[1:]) - 1
            if index < 0 or index >= len(documents):
                raise ValueError
            global_id = f"S{len(citations) + len(records) + 1}"
            record = citation_from_document(documents[index], global_id)
            if record is None:
                raise ValueError
            mapping[source_id] = global_id
            records.append(record)
            cited_documents.append(documents[index])
        if not _extractive_claims_only(answer, cited_documents):
            raise ValueError
        citations.extend(records)
        answer = SOURCE_REFERENCE.sub(lambda match: f"[{mapping[match.group(1)]}]", answer)
        return {"subquestion": question, "answer": answer,
                "source_ids": list(mapping.values()), "error": ""}
    except Exception:
        return {"subquestion": question, "answer": "", "source_ids": [],
                "error": "Generated answer was not supported by retrieved evidence and citations."}


def generate_answer(state: LAGAState, answer_generator=None, llm=None):
    citations, parts = [], []
    for bundle in state.get("retrieved_evidence", []):
        question, documents = bundle["subquestion"], bundle.get("documents", [])
        if not documents:
            parts.append({"subquestion": question, "answer": "", "source_ids": [],
                          "error": bundle.get("error") or "No authorized evidence was retrieved."})
        elif answer_generator is not None:
            parts.append(_generated_part(question, documents, answer_generator, llm, citations))
        else:
            excerpts = []
            for doc in documents:
                source_id = f"S{len(citations) + 1}"
                record = citation_from_document(doc, source_id)
                if record:
                    citations.append(record)
                    excerpts.append((source_id, record["source_text"]))
            parts.append({
                "subquestion": question, "answer": format_evidence_answer(question, excerpts),
                "source_ids": [source_id for source_id, _ in excerpts], "error": "",
            })
    answer = "\n\n".join(part["answer"] for part in parts if part["answer"])
    result = state.get("calculation")
    if result:
        amount = (
            f"Calculated late fee: USD {result.calculated_late_fee:.2f}. "
            if result.calculated_late_fee is not None else ""
        )
        answer += (
            "\n\nDeterministic calculator under N.C. G.S. §42-46 "
            f"(not a quoted lease provision): {amount}{result.explanation}"
        )
    return {"answer_parts": parts, "answer": answer, "citations": citations}


def validate_answer(state: LAGAState):
    errors = list(state.get("input_errors", [])) + list(state.get("fee_errors", []))
    citations = state.get("citations", [])
    ids = {citation["source_id"] for citation in citations}
    retry_questions = []
    documents = [
        doc for bundle in state.get("retrieved_evidence", [])
        for doc in bundle.get("documents", [])
    ]
    for citation in citations:
        if not any(citation_from_document(doc, citation["source_id"]) == citation
                   for doc in documents):
            errors.append("Citation metadata does not match retrieved evidence.")
    for part in state.get("answer_parts", []):
        sources = set(part.get("source_ids", []))
        if (
            part.get("error") or not part.get("answer") or not sources
            or set(SOURCE_REFERENCE.findall(part["answer"])) != sources
            or not sources <= ids
        ):
            errors.append(part.get("error") or f"Missing validated citations: {part['subquestion']}")
            retry_questions.append(part["subquestion"])
    if not state.get("answer_parts"):
        errors.append("There is no supported answer.")
    result = state.get("calculation")
    if state.get("fee_required"):
        if result is None:
            errors.append("Late-fee inputs could not be safely extracted.")
        elif state.get("calculations") != [result.to_dict()]:
            errors.append("Fee output did not originate from the deterministic calculator.")
        elif result.status in UNRESOLVED:
            errors.extend(result.validation_errors or [result.explanation])
        if result is None or result.status in UNRESOLVED:
            retry_questions.extend(q for q in state.get("subquestions", []) if is_fee_question(q))
    errors = list(dict.fromkeys(errors))
    activity = list(state.get("tool_activity", []))
    activity.append({
        "label": "Answer validation passed." if not errors else "Answer validation failed.",
        "status": "complete" if not errors else "attention",
    })
    return {
        "validation_status": "failed" if errors else "passed", "validation_errors": errors,
        "retry_subquestions": list(dict.fromkeys(retry_questions)), "tool_activity": activity,
    }


def prepare_retry(state: LAGAState):
    targets = state.get("retry_subquestions") or state.get("subquestions", [])
    queries = {
        question: (
            "lease agreement exact clause text, applicable conditions, fees, "
            f"dates, and exceptions: {question}"
        ) for question in targets
    }
    return {
        "retry_count": state.get("retry_count", 0) + 1, "retry_queries": queries,
        "validation_errors": [], "tool_activity": [
            *state.get("tool_activity", []),
            {"label": "One targeted evidence retry is being used.", "status": "attention"},
        ],
    }


def safe_abstain(state: LAGAState):
    result = state.get("calculation")
    if result and result.status in UNRESOLVED:
        answer = (
            "I can’t calculate a late fee without unambiguous contractual and "
            f"payment details. {result.explanation}"
        )
    else:
        answer = ABSTENTION
        if state.get("fee_errors"):
            answer += " " + " ".join(state["fee_errors"])
    return {
        "answer": answer, "citations": [], "validation_status": "abstained",
        "calculations": [result.to_dict()] if result and result.status in UNRESOLVED else [],
        "tool_activity": [
            *state.get("tool_activity", []),
            {"label": "Abstained after validation.", "status": "attention"},
        ],
    }

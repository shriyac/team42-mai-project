"""Transparent deterministic assertions, not semantic/LLM quality judgments."""
from decimal import Decimal, InvalidOperation
import re

from agent.evidence import citation_from_document, is_authorized_lease_document


def top_five(trace):
    """First-seen unique chunks across subquestions/retries, limited to five."""
    return list(dict.fromkeys(
        doc.metadata["chunk_id"] for event in trace for doc in event["documents"]
    ))[:5]


def retrieval_scores(expected, actual):
    if not expected:
        return None
    hits = len(set(expected) & set(actual[:5]))
    # Precision@5 always divides by 5; absent slots do not count as relevant.
    return {"recall_at_5": hits / len(set(expected)), "precision_at_5": hits / 5}


def numerical_match(expected, calculations):
    if expected is None:
        return None
    if len(calculations) != 1:
        return False
    actual = calculations[0]
    try:
        return (actual["status"] == expected["status"] and all(
            Decimal(actual[k]).is_finite() and Decimal(actual[k]) == Decimal(expected[k])
            for k in ("calculated_late_fee", "statutory_maximum")
        ))
    except (InvalidOperation, KeyError, TypeError, ValueError):
        return False


def assess(case, state, trace, calculator_calls):
    documents = [d for e in trace for d in e["documents"]]
    citations = state.get("citations", [])
    scope = {k: state[k] for k in ("tenant_id", "tenant_name", "lease_id")}
    checks = {}
    checks["tools"] = (
        set(case["expected_tools"]) ==
        ({"retrieval"} if trace else set()) | ({"fee_calculator"} if calculator_calls else set())
    )
    checks["calculation"] = numerical_match(
        case.get("expected_calculation"), state.get("calculations", []),
    )
    citations_valid = bool(citations) and all(
        isinstance(c.get("page_number"), int) and c["page_number"] > 0
        and all(c.get(k) for k in ("source_id", "document_id", "lease_id", "source_text", "document_title"))
        and any(citation_from_document(d, c["source_id"]) == c
                and is_authorized_lease_document(d, **scope) for d in documents)
        for c in citations
    )
    refs = set(re.findall(r"\[(S\d+)\]", state.get("answer", "")))
    citations_valid = citations_valid and refs == {c["source_id"] for c in citations}
    behavior = case["expected_behavior"]
    checks["citations"] = citations_valid if citations or behavior in {"answer", "calculation"} else None
    # Excerpt presence is structural support, NOT full semantic entailment.
    checks["groundedness"] = (
        citations_valid and all(c["source_text"] in state.get("answer", "") for c in citations)
        if citations or behavior in {"answer", "calculation"} else None
    )
    checks["answer_reference"] = (
        all(s.casefold() in state.get("answer", "").casefold()
            for s in case.get("answer_contains", []))
        if behavior == "answer" else None
    )
    checks["reference_evidence_coverage"] = (
        all(any(d.metadata.get("chunk_id") == chunk and any(
            citation_from_document(d, c["source_id"]) == c for c in citations
        ) for d in documents) for chunk in case["expected_chunk_ids"])
        if behavior in {"answer", "calculation"} else None
    )
    checks["abstention"] = None
    if behavior == "abstain":
        checks["abstention"] = state.get("validation_status") == "abstained" and not citations and not state.get("calculations")
        checks["behavior"] = checks["abstention"]
    elif behavior == "clarification":
        checks["abstention"] = (
            state.get("validation_status") == "abstained"
            or bool(re.search(r"\b(?:clarif\w*|unspecified|not specified|unfilled|unknown|missing)\b",
                              state.get("answer", ""), re.I))
        )
        checks["behavior"] = checks["abstention"] and not state.get("calculations")
    else:
        checks["behavior"] = state.get("validation_status") == "passed"
    return checks

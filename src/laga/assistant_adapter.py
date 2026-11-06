"""Strict adapter from the independent agent result to the public Answer DTO."""

from decimal import Decimal
import re
from typing import Any
import uuid

class InvalidAgentResult(ValueError):
    """An untrusted or incompatible agent result must not reach the browser."""


def _calculation(raw: dict[str, Any]) -> dict[str, Any] | None:
    """Recheck calculator provenance, then convert USD dollars to integer cents."""
    from tools.fee_calculator import FeeCalculationInput, calculate_late_fee

    if raw.get("currency") != "USD" or raw.get("monetary_unit") != "USD per monthly rental installment":
        raise InvalidAgentResult("Unknown calculator monetary unit.")
    inputs = raw["inputs"]
    verified = calculate_late_fee(FeeCalculationInput(
        monthly_rent=inputs["monthly_rent_usd"],
        due_date=inputs["due_date"],
        payment_date=inputs["payment_date"],
        contractual_fee_amount=inputs["contractual_fee_amount_usd"],
        contractual_fee_percentage=inputs["contractual_fee_percentage"],
        fee_already_charged=inputs["fee_already_charged"],
    )).to_dict()
    if raw != verified:
        raise InvalidAgentResult("Calculator result does not match deterministic replay.")
    if verified["calculated_late_fee"] is None:
        return None
    amount = Decimal(verified["calculated_late_fee"]) * Decimal("100")
    if not amount.is_finite() or amount < 0 or amount != amount.to_integral_value():
        raise InvalidAgentResult("Invalid integer-cent amount.")
    cents = int(amount)
    if cents > 2**53 - 1:
        raise InvalidAgentResult("Unsafe JSON integer.")
    scalar_inputs = {
        key: value for key, value in verified["inputs"].items()
        if isinstance(value, (str, int, bool))
    }
    scalar_inputs.update(
        calculation_status=verified["status"], formula=verified["formula"],
        statutory_maximum_usd=verified["statutory_maximum"],
    )
    return {
        "label": "North Carolina monthly rent late fee",
        "inputs": scalar_inputs,
        "result": cents,
        "currency": "USD",
        "method": "Deterministic N.C. G.S. §42-46 calculation; result is integer USD cents.",
    }


def _matches_excerpt(identity, item):
    """Independently verify a narrowed quote against server-recorded evidence."""
    original = item["identity"]
    if identity == original:
        return True
    if set(identity) != set(original) or any(
        identity[k] != v for k, v in original.items()
        if k not in {"source_text", "page_number"}
    ):
        return False
    quote = identity.get("source_text")
    if not isinstance(quote, str) or not quote.strip():
        return False
    spans = item.get("source_spans", [])
    if spans:
        return any(isinstance(s, dict) and isinstance(s.get("text"), str)
                   and quote in s["text"] and identity.get("page_number") == s.get("page_number")
                   for s in spans)
    return (
        quote in original["source_text"]
        and identity.get("page_number") == original["page_number"]
    )


def adapt_answer(
    result: dict[str, Any], *, thread_id: str, evidence: list[dict[str, Any]],
) -> dict[str, Any]:
    """Accept citations only when they exactly match authorized retrieved evidence."""
    if not isinstance(result, dict):
        raise InvalidAgentResult("Expected an agent result object.")
    status = result.get("validation_status")
    if status not in {"passed", "abstained"}:
        raise InvalidAgentResult("Agent validation has not completed safely.")
    answer = result.get("answer")
    citations = result.get("citations")
    calculations = result.get("calculations")
    activity = result.get("tool_activity")
    if (
        not isinstance(answer, str) or not answer.strip()
        or not isinstance(citations, list) or not isinstance(calculations, list)
        or not isinstance(activity, list)
    ):
        raise InvalidAgentResult("Agent response fields are missing or invalid.")
    if status == "passed" and not citations:
        raise InvalidAgentResult("A supported answer must have lease citations.")
    if status == "abstained" and citations:
        raise InvalidAgentResult("Abstention must not expose unvalidated citations.")

    public_citations, ids = [], set()
    for citation in citations:
        if not isinstance(citation, dict):
            raise InvalidAgentResult("Invalid source record.")
        source_id = citation.get("source_id")
        if not isinstance(source_id, str) or not re.fullmatch(r"S\d+", source_id) or source_id in ids:
            raise InvalidAgentResult("Invalid or repeated citation ID.")
        identity = {key: value for key, value in citation.items() if key != "source_id"}
        matching = next((item for item in evidence if _matches_excerpt(identity, item)), None)
        if matching is None:
            raise InvalidAgentResult("Citation was not retrieved from the authorized lease.")
        ids.add(source_id)
        public_citations.append({
            "id": source_id,
            "documentId": citation["document_id"],
            "title": citation["document_title"],
            "section": matching["section"],
            "page": citation["page_number"],
            "quote": citation["source_text"],
        })
    if status == "passed" and set(re.findall(r"\[(S\d+)\]", answer)) != ids:
        raise InvalidAgentResult("Answer source markers do not match its citations.")

    public_calculations = []
    if len(calculations) > 1:
        raise InvalidAgentResult("Only one monthly installment can be calculated.")
    for raw in calculations:
        if not isinstance(raw, dict):
            raise InvalidAgentResult("Invalid calculation record.")
        value = _calculation(raw)
        if value is None:
            if status == "passed":
                raise InvalidAgentResult("Unresolved calculation cannot support an answer.")
        elif status == "passed":
            public_calculations.append(value)
        # A failed validation never publishes a numeric fee.

    return {
        "id": str(uuid.uuid4()), "threadId": thread_id, "answer": answer,
        "status": "supported" if status == "passed" else "needs_clarification",
        "citations": public_citations, "calculations": public_calculations,
        "activity": activity, "compliance": {"status": "unavailable"},
    }

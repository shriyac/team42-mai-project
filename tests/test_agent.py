from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import pytest

from agent.graph import build_graph, run_laga_agent
from agent.nodes import MockLeaseRetrieverFactory, split_question
from tools.fee_calculator import (
    STATUS_CLARIFICATION_REQUIRED,
    STATUS_FEE_CALCULATED,
    calculate_late_fee,
)


@dataclass
class MockDocument:
    page_content: str
    metadata: dict


def make_document(
    *,
    quote: str,
    document_id: str = "lease-document-1",
    lease_id: str = "lease-1",
    tenant_id: str = "tenant-1",
    tenant_name: str = "Maya Chen",
    page: int = 2,
    clause_id: str = "8.1",
):
    return MockDocument(
        page_content=quote,
        metadata={
            "document_id": document_id,
            "chunk_id": f"{document_id}-{clause_id}-{page}",
            "lease_id": lease_id,
            "tenant_id": tenant_id,
            "tenant_name": tenant_name,
            "page_number": page,
            "clause_id": clause_id,
            "document_title": "Residential Lease",
            "document_type": "lease",
            "source_spans": [{"page_number": page, "text": quote}],
        },
    )


def request_state(question, **extra):
    state = {
        "question": question,
        "tenant_id": "tenant-1",
        "tenant_name": "Maya Chen",
        "lease_id": "lease-1",
        "as_of": "2026-01-06",
    }
    state.update(extra)
    return state


def test_simple_pet_policy_question_returns_cited_lease_evidence():
    evidence = make_document(
        quote="One pet is allowed with prior written approval."
    )
    factory = MockLeaseRetrieverFactory([evidence])

    result = run_laga_agent(
        "What does my lease say about pets?",
        "tenant-1",
        "Maya Chen",
        "lease-1",
        "2026-01-06",
        retriever_factory=factory,
    )

    assert result["validation_status"] == "passed"
    assert "One pet is allowed with prior written approval." in result["answer"]
    assert result["citations"][0]["document_id"] == "lease-document-1"
    assert result["citations"][0]["page_number"] == 2
    assert result["citations"][0]["clause_id"] == "8.1"
    assert result["citations"][0]["source_text"] == evidence.page_content


def test_multi_part_question_is_split_and_retrieved_per_subquestion():
    rent_q = "What is the monthly rent"
    pet_q = "what is the pet rule?"
    rent_doc = make_document(
        quote="Monthly rent is $1,200.00.",
        clause_id="3.1",
        page=3,
    )
    pet_doc = make_document(
        quote="One pet is allowed with prior written approval.",
        clause_id="8.1",
        page=8,
    )
    factory = MockLeaseRetrieverFactory(
        results_by_query={rent_q: [rent_doc], pet_q: [pet_doc]}
    )
    graph = build_graph(retriever_factory=factory)

    state = graph.invoke(
        request_state("What is the monthly rent, and what is the pet rule?")
    )

    assert split_question("What is the monthly rent, and what is the pet rule?") == [
        rent_q,
        pet_q,
    ]
    assert factory.queries == [rent_q, pet_q]
    assert state["validation_status"] == "passed"
    assert len(state["citations"]) == 2
    assert "[S1]" in state["answer"] and "[S2]" in state["answer"]


def test_late_fee_question_extracts_evidence_and_invokes_calculator():
    evidence = make_document(
        quote=(
            "Monthly rent is $1,000.00. Rent is payable on the first day of each "
            "month. A flat late fee of $20.00 applies."
        ),
        clause_id="3.1",
        page=3,
    )
    factory = MockLeaseRetrieverFactory([evidence])
    calculator_calls = []

    def calculator(inputs):
        calculator_calls.append(inputs)
        return calculate_late_fee(inputs)

    graph = build_graph(retriever_factory=factory, fee_calculator=calculator)

    state = graph.invoke(
        request_state(
            "For rent due on 2026-01-01, I paid on 2026-01-06 and have not paid a late fee. "
            "What is my late fee?"
        )
    )

    assert state["validation_status"] == "passed"
    assert state["calculation"].status == STATUS_FEE_CALCULATED
    assert state["calculations"][0]["calculated_late_fee"] == "20.00"
    assert len(calculator_calls) == 1
    assert calculator_calls[0].monthly_rent == Decimal("1000.00")
    assert calculator_calls[0].due_date == date(2026, 1, 1)
    assert calculator_calls[0].payment_date == date(2026, 1, 6)
    assert calculator_calls[0].fee_already_charged is False
    assert "Deterministic fee calculator invoked." in [
        item["label"] for item in state["tool_activity"]
    ]
    assert "USD 20.00" in state["answer"]


def test_missing_contractual_fee_terms_are_not_guessed():
    evidence = make_document(
        quote=(
            "Monthly rent is $1,000.00. Rent is payable on the first day of each "
            "month. The lease does not state a late fee."
        ),
        clause_id="3.1",
        page=3,
    )
    factory = MockLeaseRetrieverFactory([evidence])
    graph = build_graph(retriever_factory=factory)

    state = graph.invoke(
        request_state(
            "For rent due on 2026-01-01, I paid on 2026-01-06 and have not paid a late fee. "
            "What is my late fee?"
        )
    )

    assert state["calculation"].status == STATUS_CLARIFICATION_REQUIRED
    assert state["calculations"][0]["calculated_late_fee"] is None
    assert "no contractual term has been inferred" in state["calculations"][0]["explanation"]
    assert state["validation_status"] == "abstained"
    assert "unambiguous contractual and payment details" in state["answer"]


def test_unsupported_question_retries_once_then_abstains():
    factory = MockLeaseRetrieverFactory([])
    result = run_laga_agent(
        "Does my lease include a rooftop pool?",
        "tenant-1",
        "Maya Chen",
        "lease-1",
        "2026-01-06",
        retriever_factory=factory,
    )

    assert result["validation_status"] == "abstained"
    assert result["citations"] == []
    assert "can’t answer" in result["answer"]
    assert len(factory.queries) == 2
    assert "exact clause text" in factory.queries[1]


def test_invalid_citation_is_rejected_and_retried():
    evidence = make_document(quote="One pet is allowed with approval.")
    factory = MockLeaseRetrieverFactory([evidence])

    def bad_answer_generator(question, documents, llm):
        return {
            "answer": "Pets are unrestricted [S99].",
            "citations": [{"source_id": "S99"}],
        }

    graph = build_graph(
        retriever_factory=factory,
        answer_generator=bad_answer_generator,
    )
    state = graph.invoke(request_state("Is a pet allowed?"))

    assert state["validation_status"] == "abstained"
    assert state["citations"] == []
    assert "retrieved evidence" in " ".join(state["validation_errors"]).lower()
    assert len(factory.queries) == 2


def test_retriever_filters_other_tenants_and_leases():
    authorized = make_document(quote="My lease says quiet hours begin at 10 PM.")
    other_lease = make_document(
        quote="Other tenant evidence.",
        document_id="lease-document-2",
        lease_id="lease-2",
        tenant_id="tenant-2",
        tenant_name="James Wilson",
    )
    wrong_tenant_same_lease = make_document(
        quote="Wrong tenant evidence.",
        document_id="lease-document-3",
        tenant_id="tenant-2",
        tenant_name="James Wilson",
    )
    factory = MockLeaseRetrieverFactory(
        [authorized, other_lease, wrong_tenant_same_lease]
    )

    result = run_laga_agent(
        "When do quiet hours begin?",
        "tenant-1",
        "Maya Chen",
        "lease-1",
        "2026-01-06",
        retriever_factory=factory,
    )

    assert result["validation_status"] == "passed"
    assert [item["document_id"] for item in result["citations"]] == [
        "lease-document-1"
    ]
    assert "Other tenant evidence." not in result["answer"]
    assert "Wrong tenant evidence." not in result["answer"]


def test_retry_count_is_bounded_to_one():
    question = "What are the lease pet rules?"
    retry_query = (
        "lease agreement exact clause text, applicable conditions, fees, dates, "
        f"and exceptions: {question}"
    )
    evidence = make_document(quote="One pet is allowed with approval.")
    factory = MockLeaseRetrieverFactory(
        results_by_query={question: [], retry_query: [evidence]}
    )
    graph = build_graph(retriever_factory=factory)

    state = graph.invoke(request_state(question))

    assert state["retry_count"] == 1
    assert len(factory.queries) == 2
    assert state["validation_status"] == "passed"
    assert len(state["citations"]) == 1


@pytest.mark.parametrize(
    ("fee_clause", "expected_fee"),
    [
        ("A late fee of 5% of monthly rent applies.", "50.00"),
        ("A flat late fee of $100.00 applies.", "50.00"),
    ],
)
def test_extracted_percentage_and_capped_flat_fees(fee_clause, expected_fee):
    factory = MockLeaseRetrieverFactory([
        make_document(quote=f"Monthly rent is $1,000.00. {fee_clause}")
    ])
    state = build_graph(retriever_factory=factory).invoke(request_state(
        "For rent due on 2026-01-01, I paid on 2026-01-06 and "
        "have not paid a late fee. What is the late fee?"
    ))
    assert state["validation_status"] == "passed"
    assert state["calculations"][0]["calculated_late_fee"] == expected_fee
    assert state["calculations"] == [state["calculation"].to_dict()]


@pytest.mark.parametrize("fee_clause", [
    "A late fee of $20 or 5% of monthly rent applies.",
    "A late fee of up to $50 applies.",
    "A late fee of $20 applies after ten days.",
    "A late fee of 5% of the unpaid balance applies.",
    "No late fee of $20 is authorized.",
])
def test_ambiguous_or_unrepresentable_contract_terms_require_clarification(fee_clause):
    factory = MockLeaseRetrieverFactory([
        make_document(quote=f"Monthly rent is $1,000.00. {fee_clause}")
    ])
    state = build_graph(retriever_factory=factory).invoke(request_state(
        "For rent due on 2026-01-01, I paid on 2026-01-06 and "
        "have not paid a late fee. What is the late fee?"
    ))
    assert state["validation_status"] == "abstained"
    assert state["calculation"] is None
    assert state["calculations"] == []
    assert state["fee_errors"]


@pytest.mark.parametrize("question", [
    "I paid on 2026-01-06 and have not paid a late fee. What is the late fee?",
    "For rent due on 2026-01-01, I have not paid a late fee. What is the late fee?",
    "For rent due on 2026-01-01, I paid on 2026-01-06. What is the late fee?",
])
def test_missing_payment_facts_are_not_inferred_from_as_of(question):
    factory = MockLeaseRetrieverFactory([make_document(quote=(
        "Monthly rent is $1,000.00. Rent is due on the first day of each month. "
        "A late fee of $20 applies."
    ))])
    state = build_graph(retriever_factory=factory).invoke(request_state(question))
    assert state["validation_status"] == "abstained"
    assert state["calculation"] is None
    assert state["fee_errors"]


@pytest.mark.parametrize(("answer", "status"), [
    ("One pet is allowed with approval [S1].", "passed"),
    ("Pets are unrestricted [S1].", "abstained"),
])
def test_valid_citation_does_not_make_an_unsupported_claim_grounded(answer, status):
    factory = MockLeaseRetrieverFactory([
        make_document(quote="One pet is allowed with approval.")
    ])

    def answerer(question, documents, llm):
        return {"answer": answer, "citations": [{"source_id": "S1"}]}

    result = build_graph(
        retriever_factory=factory, answer_generator=answerer,
    ).invoke(request_state("Is a pet allowed?"))
    assert result["validation_status"] == status
    if status == "abstained":
        assert result["citations"] == []
        assert "Pets are unrestricted" not in result["answer"]


def test_missing_trusted_scope_fails_without_retrieval_or_retry():
    factory = MockLeaseRetrieverFactory([])
    state = build_graph(retriever_factory=factory).invoke({
        "question": "Is a pet allowed?", "as_of": "2026-01-06",
    })
    assert state["validation_status"] == "abstained"
    assert state["retry_count"] == 0
    assert factory.calls == []


def test_generated_claim_must_match_the_cited_document_not_an_uncited_one():
    factory = MockLeaseRetrieverFactory([
        make_document(quote="One pet is allowed with approval.", clause_id="8.1"),
        make_document(quote="Quiet hours begin at 10 PM.", clause_id="9.1"),
    ])

    def wrong_source(question, documents, llm):
        return {
            "answer": "Quiet hours begin at 10 PM [S1].",
            "citations": [{"source_id": "S1"}],
        }

    state = build_graph(
        retriever_factory=factory, answer_generator=wrong_source,
    ).invoke(request_state("When are quiet hours?"))
    assert state["validation_status"] == "abstained"
    assert state["citations"] == []


@pytest.mark.parametrize("rent", ["1e3", "1,00", "1000abc"])
def test_unrecognized_monetary_text_is_not_partially_parsed(rent):
    factory = MockLeaseRetrieverFactory([
        make_document(quote=f"Monthly rent is ${rent}. A late fee of $20 applies.")
    ])
    state = build_graph(retriever_factory=factory).invoke(request_state(
        "For rent due on 2026-01-01, I paid on 2026-01-06 and "
        "have not paid a late fee. What is the late fee?"
    ))
    assert state["validation_status"] == "abstained"
    assert state["calculation"] is None

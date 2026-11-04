from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from laga_agent.graph import build_lease_graph, split_question
from tools.fee_calculator import (
    FeeCalculationInput,
    STATUS_CLARIFICATION_REQUIRED,
    STATUS_FEE_CALCULATED,
)


@dataclass
class MockDocument:
    page_content: str
    metadata: dict


class MockRetriever:
    def __init__(self, documents_by_question):
        self.documents_by_question = documents_by_question
        self.queries = []

    def invoke(self, query):
        self.queries.append(query)
        return self.documents_by_question.get(query, [])


class MockRetrieverFactory:
    def __init__(self, documents_by_question):
        self.retriever = MockRetriever(documents_by_question)
        self.calls = []

    def __call__(self, tenant_name, document_ids):
        self.calls.append((tenant_name, document_ids))
        return self.retriever


def make_document(
    chunk_id="chunk-1",
    document_id="lease-doc-1",
    quote="Monthly rent is $1,000.",
    section="3.1",
    page=3,
):
    return MockDocument(
        page_content=quote,
        metadata={
            "chunk_id": chunk_id,
            "document_id": document_id,
            "document_title": "Residential Lease",
            "section_id": section,
            "section_title": "Rent and payment",
            "page_numbers": [page],
            "source_spans": [{"page_number": page, "text": quote}],
        },
    )


def invoke_graph(factory, question, **extra):
    graph = build_lease_graph(retriever_factory=factory)
    request = {
        "question": question,
        "tenant_name": "Maya Chen",
        "document_ids": ["lease-doc-1"],
        "scope": {"type": "lease", "id": "lease-1"},
        "asOf": "2026-02-01",
        "threadId": "thread-1",
    }
    request.update(extra)
    return graph.invoke(request)["response"]


def test_simple_lease_retrieval_returns_ui_compatible_citation():
    factory = MockRetrieverFactory(
        {"What is the monthly rent?": [make_document()]}
    )

    response = invoke_graph(factory, "What is the monthly rent?")

    assert response["status"] == "supported"
    assert "Monthly rent is $1,000." in response["answer"]
    assert response["citations"] == [
        {
            "id": "S1",
            "title": "Residential Lease",
            "section": "3.1",
            "page": 3,
            "quote": "Monthly rent is $1,000.",
            "documentId": "lease-doc-1",
        }
    ]
    assert factory.calls == [("Maya Chen", ["lease-doc-1"])]


def test_multi_part_question_retrieves_each_part_and_combines_evidence():
    first = "What is the rent"
    second = "when is it due?"
    factory = MockRetrieverFactory(
        {
            first: [make_document(chunk_id="rent", quote="Rent is $1,000.")],
            second: [
                make_document(
                    chunk_id="due",
                    quote="Rent is due on the first day of each month.",
                    section="3.2",
                    page=4,
                )
            ],
        }
    )

    response = invoke_graph(
        factory, "What is the rent, and when is it due?"
    )

    assert split_question("What is the rent, and when is it due?") == [
        first,
        second,
    ]
    assert factory.retriever.queries == [first, second]
    assert response["status"] == "supported"
    assert len(response["citations"]) == 2
    assert "[S1]" in response["answer"]
    assert "[S2]" in response["answer"]


def test_fee_question_invokes_existing_deterministic_calculator():
    factory = MockRetrieverFactory(
        {"What is the late fee?": [make_document(quote="Late fee is $20.")]}
    )
    fee_input = FeeCalculationInput(
        monthly_rent=Decimal("1000.00"),
        due_date=date(2026, 1, 1),
        payment_date=date(2026, 1, 6),
        contractual_fee_amount=Decimal("20.00"),
    )

    response = invoke_graph(
        factory,
        "What is the late fee?",
        fee_input=fee_input,
    )

    assert response["status"] == "supported"
    assert len(response["calculations"]) == 1
    assert response["calculations"][0]["result"] == 2000
    assert response["calculations"][0]["currency"] == "USD"
    assert (
        response["calculations"][0]["inputs"]["calculation_status"]
        == STATUS_FEE_CALCULATED
    )
    assert "USD 20.00" in response["answer"]


def test_missing_contractual_terms_are_returned_as_calculator_clarification():
    factory = MockRetrieverFactory(
        {"What late fee is allowed?": [make_document()]}
    )
    fee_input = FeeCalculationInput(
        monthly_rent=Decimal("1000.00"),
        due_date=date(2026, 1, 1),
        payment_date=date(2026, 1, 6),
    )

    graph = build_lease_graph(retriever_factory=factory)
    state = graph.invoke(
        {
            "question": "What late fee is allowed?",
            "tenant_name": "Maya Chen",
            "document_ids": ["lease-doc-1"],
            "scope": {"type": "lease", "id": "lease-1"},
            "fee_input": fee_input,
        }
    )
    response = state["response"]
    fee_result = state["fee_result"].to_dict()

    assert response["status"] == "needs_clarification"
    assert response["calculations"] == []
    assert fee_result["status"] == STATUS_CLARIFICATION_REQUIRED
    assert fee_result["calculated_late_fee"] is None
    assert "no contractual term has been inferred" in response["answer"]


def test_no_retrieved_evidence_abstains_without_citations():
    factory = MockRetrieverFactory({"What does my lease say?": []})

    response = invoke_graph(factory, "What does my lease say?")

    assert response["status"] == "needs_clarification"
    assert "can’t answer" in response["answer"]
    assert response["citations"] == []


def test_answer_generator_claim_without_valid_citation_is_withheld():
    factory = MockRetrieverFactory(
        {"Is a pet allowed?": [make_document(quote="No pet term found in excerpt.")]}
    )

    def unsupported_generator(question, documents, llm):
        return {"answer": "Pets are permitted [S9].", "citations": [{"source_id": "S9"}]}

    graph = build_lease_graph(
        retriever_factory=factory,
        answer_generator=unsupported_generator,
    )
    response = graph.invoke(
        {
            "question": "Is a pet allowed?",
            "tenant_name": "Maya Chen",
            "document_ids": ["lease-doc-1"],
            "scope": {"type": "lease", "id": "lease-1"},
        }
    )["response"]

    assert response["status"] == "needs_clarification"
    assert "could not be matched to retrieved citations" in response["answer"]
    assert response["citations"] == []


def test_missing_trusted_tenant_context_skips_retrieval():
    factory = MockRetrieverFactory({"What does my lease say?": [make_document()]})
    graph = build_lease_graph(retriever_factory=factory)

    response = graph.invoke({"question": "What does my lease say?"})["response"]

    assert response["status"] == "needs_clarification"
    assert "Trusted tenant identity is missing" in response["answer"]
    assert factory.calls == []

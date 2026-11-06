"""Question relevance is separate from citation validity and authorization."""

import pytest

from agent.graph import build_graph
from agent.nodes import MockLeaseRetrieverFactory
from src.laga.assistant_adapter import _matches_excerpt
from test_agent import make_document, request_state
from test_assistant_integration import system, ask, checked


def run(question, documents, answerer=None):
    factory = MockLeaseRetrieverFactory(documents)
    result = build_graph(retriever_factory=factory, answer_generator=answerer).invoke(
        request_state(question))
    return result, factory


@pytest.mark.parametrize("question", [
    "What is the Wi-Fi password for my apartment?",
    "What is the Wi-Fi password for my home?",
])
def test_wifi_password_is_not_supported_by_internet_or_pet_terms(question):
    result, factory = run(question, [make_document(
        quote="Tenant pays internet. One pet is allowed with prior written approval.")])
    assert result["validation_status"] == "abstained"
    assert result["answer"] == "The available lease documents do not provide a verified Wi-Fi password."
    assert result["citations"] == []
    assert result["retry_count"] == 1
    assert len(factory.queries) == 2
    assert result["retrieved_evidence"][0]["documents"]  # diagnostic provenance retained


def test_valid_but_irrelevant_evidence_does_not_answer_question():
    result, _ = run("When does my lease expire?", [
        make_document(quote="One pet is allowed with prior written approval.")])
    assert result["validation_status"] == "abstained"
    assert not result["citations"]


def test_valid_citation_cannot_support_an_invented_expiration_date():
    def invented(question, docs, llm):
        return {"answer": "Lease ends on 2030-01-31 [S1].", "citations": ["S1"]}
    result, _ = run("When does my lease expire?", [
        make_document(quote="Lease ends on 2027-01-31.")], invented)
    assert result["validation_status"] == "abstained"
    assert "2030" not in result["answer"]


def test_partially_supported_multi_question_abstains_without_partial_proof():
    result, _ = run("When does my lease end, and what is the Wi-Fi password?", [
        make_document(quote="Lease ends on 2027-01-31.")])
    assert result["validation_status"] == "abstained"
    assert result["citations"] == []


def test_fully_supported_multi_question_uses_only_relevant_clauses():
    result, _ = run("When does my lease end, and what happens to my security deposit?", [
        make_document(quote="Lease ends on 2027-01-31.", clause_id="3"),
        make_document(quote="The security deposit may be deducted for documented damage.", clause_id="4"),
        make_document(quote="One pet is allowed with prior written approval.", clause_id="11"),
    ])
    assert result["validation_status"] == "passed"
    assert len(result["citations"]) == 2
    assert "pet" not in result["answer"]


def test_relevant_expiration_excerpt_keeps_real_page_and_omits_unrelated_text():
    text = "Lease ends on 2027-01-31.\n\nTenant pays internet."
    result, _ = run("When does my lease expire?", [make_document(quote=text, page=7)])
    assert result["validation_status"] == "passed"
    assert result["citations"][0]["page_number"] == 7
    assert result["citations"][0]["source_text"] == "Lease ends on 2027-01-31."
    assert "internet" not in result["answer"]


def test_relevant_pet_policy_remains_supported():
    result, _ = run("Are pets allowed under my lease?", [
        make_document(quote="One pet is allowed with prior written approval.")])
    assert result["validation_status"] == "passed"


@pytest.mark.parametrize("question,unchecked,operative", [
    ("Are pets allowed under my lease?", "☐ - No Pets Allowed.",
     "One pet is allowed with prior written approval."),
    ("What are my lease's late payment terms?", "☐ - No Late Fee.",
     "A late fee of $50 applies once per installment after five calendar days."),
])
def test_unchecked_template_option_is_not_an_operative_term(question, unchecked, operative):
    result, _ = run(question, [
        make_document(quote=unchecked, clause_id="unchecked"),
        make_document(quote=operative, clause_id="selected"),
    ])
    assert result["validation_status"] == "passed"
    assert result["citations"][0]["source_text"] == operative


def test_unchecked_option_alone_requires_clarification():
    result, _ = run("Are pets allowed?", [make_document(quote="☐ - Pets allowed.")])
    assert result["validation_status"] == "abstained"


def test_incomplete_deposit_fragment_is_not_an_answer():
    result, _ = run("What happens to my security deposit?", [
        make_document(quote="The security deposit is returned to the Tenant in")])
    assert result["validation_status"] == "abstained"


@pytest.mark.parametrize("question,quote", [
    ("Are pets allowed?", "One-time nonrefundable pet fee: $250.00."),
    ("Are pets allowed?", "Tenant indemnifies the landlord for actions of any pet allowed on the property."),
    ("What are my late payment terms?", "No percentage late fee; no daily compounding."),
    ("What happens to my security deposit?",
     "The security deposit is returned in accordance with the timeframe mentioned."),
])
def test_related_but_nonresponsive_terms_do_not_establish_answerability(question, quote):
    result, _ = run(question, [make_document(quote=quote)])
    assert result["validation_status"] == "abstained"


def test_unavailable_term_is_not_a_supported_substantive_answer():
    result, _ = run("What is my security deposit amount?", [
        make_document(quote="Security deposit amount is not specified.")])
    assert result["validation_status"] == "abstained"


def test_foreign_evidence_cannot_satisfy_missing_lease_term():
    result, _ = run("When does my lease expire?", [
        make_document(quote="One pet is allowed with approval."),
        make_document(quote="Lease ends on 2027-01-31.", tenant_id="tenant-2",
                      tenant_name="Other Tenant"),
    ])
    assert result["validation_status"] == "abstained"
    assert not result["citations"]


def test_wifi_backend_status_and_no_unrelated_citations(system):
    # Existing deterministic integration fixture returns valid pet evidence.
    answer = checked(ask(system.client(), question="What is the Wi-Fi password for my apartment?"))
    assert answer["status"] == "needs_clarification"
    assert answer["citations"] == []
    assert "verified Wi-Fi password" in answer["answer"]


def test_excerpt_adapter_rejects_forged_quote_or_page():
    original = {"source_text": "Lease ends on 2027-01-31.\n\nTenant pays internet.",
                "page_number": 7, "document_id": "lease-document-1"}
    item = {"identity": original, "source_spans": [
        {"text": original["source_text"], "page_number": 7}]}
    excerpt = {**original, "source_text": "Lease ends on 2027-01-31."}
    assert _matches_excerpt(excerpt, item)
    assert not _matches_excerpt({**excerpt, "page_number": 8}, item)
    assert not _matches_excerpt({**excerpt, "source_text": "Lease ends on 2030-01-31."}, item)

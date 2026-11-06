"""Evaluation harness regressions. Use the secret-isolated launcher, never live keys."""

from types import SimpleNamespace

import pytest

from evaluation.fixtures import mock_backend
from evaluation.metrics import assess
from evaluation.run_evals import execute_case, load_dataset, summarize, evaluate
from agent.evidence import citation_from_document


def test_denial_exercises_actual_backend_api_and_never_builds_retriever(tmp_path, monkeypatch):
    backend = mock_backend(tmp_path)
    original = backend.post_assistant_messages
    calls = []

    def checked(**kwargs):
        calls.append(kwargs)
        return original(**kwargs)

    monkeypatch.setattr(backend, "post_assistant_messages", checked)
    case = load_dataset()["cases"][-1]
    result = execute_case(case, backend, lambda *a: pytest.fail("Foreign lease must not retrieve."))
    assert calls[0]["user"] == {"id": "tenant-1"}
    assert calls[0]["scope"] == {"type": "lease", "id": "lease-2"}
    assert result["status"] == "PASSED"
    assert result["authorization_interface"] == "BackendAPI.post_assistant_messages"
    assert result["http_equivalent_status"] == 404
    assert result["actual_tool_calls"] == []


def test_factual_rubric_rejects_pet_permission_as_damage_answer():
    doc = SimpleNamespace(
        page_content="One pet is allowed with prior written approval.",
        metadata={"chunk_id": "synthetic-pet-clause", "document_id": "lease-document-1",
                  "lease_id": "lease-1", "tenant_id": "tenant-1",
                  "tenant_name": "Maya Chen", "page_number": 2, "clause_id": "8.1",
                  "document_title": "Synthetic lease", "document_type": "lease"},
    )
    citation = citation_from_document(doc, "S1")
    case = {"expected_tools": ["retrieval"], "expected_behavior": "answer",
            "expected_chunk_ids": [doc.metadata["chunk_id"]],
            "answer_contains": ["prior written approval", "pet-related damage"]}
    state = {"tenant_id": "tenant-1", "tenant_name": "Maya Chen", "lease_id": "lease-1",
             "validation_status": "passed", "answer": doc.page_content + " [S1]",
             "citations": [citation], "calculations": []}
    checks = assess(case, state, [{"documents": [doc]}], [])
    assert checks["citations"]
    assert checks["factual_support"] is False


def test_no_numeric_expectation_is_not_measured_not_perfect_accuracy():
    outcomes = [{"status": "PASSED", "executed": True, "latency_seconds": 1.0,
                 "checks": {"calculation": None}}]
    summary = summarize(outcomes)
    assert summary["metrics"]["calculation_exact_match"] == {
        "passed": 0, "denominator": 0, "value": None, "measurement_status": "NOT_MEASURED"}


def test_blocked_live_never_falls_back_to_offline(monkeypatch):
    monkeypatch.setenv("LAGA_RAG_ENABLED", "false")
    monkeypatch.setattr("evaluation.run_evals.FixtureFactory",
                        lambda *a: pytest.fail("No live fallback is allowed."))
    result = evaluate("live")
    assert result["execution_mode"] == "LIVE"
    assert result["summary"]["blocked"] == 10
    assert result["summary"]["not_run"] == 10
    assert result["summary"]["questions_executed"] == 0
    assert all("BLOCKED" in o["reason"] for o in result["outcomes"])


def test_supported_status_cannot_override_false_factual_rubric(tmp_path):
    result = evaluate("offline")
    for outcome in result["outcomes"]:
        if outcome.get("checks", {}).get("factual_support") is False:
            assert outcome["status"] == "FAILED"
            assert "factual_support" in outcome["failure_reasons"]

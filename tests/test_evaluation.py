"""Evaluation regression tests, run only via the existing isolated test launcher."""
from copy import deepcopy
import json

import pytest

from evaluation.fixtures import canonical_documents, mock_backend
from evaluation.metrics import numerical_match, retrieval_scores, assess
from agent.evidence import citation_from_document
from test_agent import make_document
from evaluation.run_evals import evaluate, live_backend, load_dataset, save_reports
from laga.backend_api import APIError


def test_dataset_has_exact_requested_categories_and_real_chunk_references():
    dataset = load_dataset()
    counts = {}
    for c in dataset["cases"]:
        counts[c["category"]] = counts.get(c["category"], 0) + 1
    assert counts == {"simple_clause": 3, "multi_clause": 2, "fee_calculation": 2,
                      "missing_information": 2, "tenant_authorization": 1}
    chunks = {d.metadata["chunk_id"]: d for d in canonical_documents(dataset["source"])}
    for case in dataset["cases"]:
        assert set(case["expected_chunk_ids"]) <= chunks.keys()
        # Literal expected answer fragments really occur in annotated evidence.
        evidence = " ".join(chunks[k].metadata["source_text"] for k in case["expected_chunk_ids"])
        assert all(v.casefold() in evidence.casefold() for v in case["answer_contains"])


def test_changed_pdf_fails_closed():
    source = {**load_dataset()["source"], "sha256": "0" * 64}
    with pytest.raises(ValueError, match="changed"):
        canonical_documents(source)


def test_metrics_use_exact_decimal_and_explicit_precision_denominator():
    assert retrieval_scores(["a", "b"], ["a"]) == {"recall_at_5": 0.5, "precision_at_5": 0.2}
    assert retrieval_scores([], []) is None
    expected = {"status": "fee_calculated", "calculated_late_fee": "50.00", "statutory_maximum": "110.00"}
    assert numerical_match(expected, [{**expected, "calculated_late_fee": "50.000"}])
    assert not numerical_match(expected, [{**expected, "calculated_late_fee": "50.001"}])
    assert not numerical_match(expected, [{**expected, "calculated_late_fee": "NaN"}])
    assert not numerical_match(expected, [])
    assert numerical_match(None, []) is None


def test_mock_uses_backend_denial_before_retrieval(tmp_path):
    backend = mock_backend(tmp_path)
    principal, _, lease = backend.authorize("tenant-1", "lease-1")
    assert principal["name"] == "Maya Chen"
    assert lease["tenantId"] == principal["id"]
    with pytest.raises(APIError) as error:
        backend.authorize("tenant-2", "lease-1")
    assert error.value.status == 404


def test_disabled_live_never_initializes_production_clients(monkeypatch):
    monkeypatch.setenv("LAGA_RAG_ENABLED", "false")
    monkeypatch.setattr("evaluation.run_evals.load_configuration",
                        lambda: pytest.fail("Disabled evaluation must not load clients/config."))
    backend, reason = live_backend()
    assert backend is None
    assert "disabled" in reason
    result = evaluate("live")
    assert result["summary"]["not_run"] == 10
    assert result["summary"]["questions_executed"] == 0
    assert all(o["status"] == "NOT_RUN" for o in result["outcomes"])
    assert result["summary"]["metrics"]["recall_at_5"]["value"] is None


def test_mock_outcomes_are_measured_not_assumed_and_reports_preserve_modes(tmp_path, monkeypatch):
    monkeypatch.setenv("LAGA_RAG_ENABLED", "false")
    result = evaluate("mock")
    assert result["summary"]["questions_executed"] == 10
    assert result["summary"]["passed"] + result["summary"]["failed"] == 10
    denied = next(o for o in result["outcomes"] if o["question_id"] == "Q10")
    assert denied["status"] == "PASSED"
    assert denied["retrieved_chunks"] == []
    for outcome in result["outcomes"]:
        checks = outcome["checks"]
        assert (outcome["status"] == "FAILED") == (False in checks.values())
    save_reports(result, tmp_path)
    save_reports(evaluate("live"), tmp_path)
    saved = json.loads((tmp_path / "results.json").read_text())
    assert set(saved["runs"]) == {"mock", "live"}
    assert "NOT_RUN" in (tmp_path / "report.md").read_text()


def test_needs_annotation_is_never_passed():
    dataset = deepcopy(load_dataset())
    dataset["cases"][0]["annotation_status"] = "needs_annotation"
    result = evaluate("mock", dataset)
    assert result["outcomes"][0]["status"] == "NOT_RUN"
    assert result["summary"]["questions_executed"] == 9


def test_offline_alias_is_labeled_and_metrics_expose_denominators():
    result = evaluate("offline")
    assert result["execution_mode"] == "OFFLINE"
    assert result["summary"]["total_cases"] == 10
    assert result["summary"]["metrics"]["overall_case_pass_rate"]["denominator"] == 10
    wifi = next(o for o in result["outcomes"] if o["question_id"] == "Q08")
    assert wifi["response_status"] == "needs_clarification"
    assert wifi["retrieval_measurement_status"] == "NOT_MEASURED"
    assert wifi["retrieval_scores"] is None
    assert len(wifi["actual_tool_calls"]) == 2


def test_exact_excerpt_citations_score_correctly_but_wrong_page_does_not():
    doc = make_document(quote="Lease ends on 2027-01-31.\n\nTenant pays internet.", page=3)
    citation = citation_from_document(doc, "S1")
    citation["source_text"] = "Lease ends on 2027-01-31."
    case = {"expected_tools": ["retrieval"], "expected_behavior": "answer",
            "expected_chunk_ids": [doc.metadata["chunk_id"]], "answer_contains": ["2027-01-31"]}
    state = {"tenant_id": "tenant-1", "tenant_name": "Maya Chen", "lease_id": "lease-1",
             "validation_status": "passed", "answer": "Lease ends on 2027-01-31. [S1]",
             "citations": [citation], "calculations": []}
    trace = [{"documents": [doc]}]
    assert assess(case, state, trace, [])["citations"]
    assert assess(case, state, trace, [])["returned_citations"]
    assert assess(case, state, trace, [])["reference_evidence_coverage"]
    citation["page_number"] = 4
    assert not assess(case, state, trace, [])["citations"]
    assert not assess(case, state, trace, [])["returned_citations"]


def test_supported_uncertainty_word_is_not_counted_as_safe_abstention():
    case = {"expected_tools": ["retrieval"], "expected_behavior": "clarification",
            "expected_chunk_ids": []}
    state = {"tenant_id": "tenant-1", "tenant_name": "Maya Chen", "lease_id": "lease-1",
             "validation_status": "passed", "answer": "An unspecified charge applies.",
             "citations": [], "calculations": []}
    assert assess(case, state, [{"documents": []}], [])["abstention"] is False


def test_reports_discard_results_from_different_dataset(tmp_path):
    result = evaluate("offline")
    (tmp_path / "results.json").write_text(json.dumps({
        "runs": {"live": {"dataset_fingerprint": "old-dataset", "outcomes": []}}}))
    save_reports(result, tmp_path)
    saved = json.loads((tmp_path / "results.json").read_text())
    assert set(saved["runs"]) == {"mock"}
    assert "OFFLINE" in (tmp_path / "report.md").read_text()

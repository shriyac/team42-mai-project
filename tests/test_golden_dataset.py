"""Dataset annotation verification only: no graph evaluation or live clients."""

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

import pytest

from evaluation.fixtures import ROOT, canonical_documents, mock_backend
from evaluation.run_evals import load_dataset
from laga.backend_api import APIError
from tools.fee_calculator import FeeCalculationInput, calculate_late_fee


def test_requested_ids_categories_and_annotation_completeness():
    data = load_dataset()
    assert [c["id"] for c in data["cases"]] == [f"Q{n:02}" for n in range(1, 11)]
    assert len({c["id"] for c in data["cases"]}) == 10
    assert [c["category"] for c in data["cases"]] == (
        ["simple_clause"] * 3 + ["multi_clause"] * 2 + ["fee_calculation"] * 2
        + ["missing_information"] * 2 + ["tenant_authorization"]
    )
    assert all(c["annotation_status"] == "verified" for c in data["cases"])
    assert all(c["tenant_id"] == "tenant-1" for c in data["cases"])
    assert data["cases"][-1]["lease_id"] == "lease-2"


def test_canonical_document_hash_manifest_and_every_page_quote_match():
    data = load_dataset()
    assert sha256((ROOT / data["source"]["manifest"]).read_bytes()).hexdigest() == data["source"]["manifest_sha256"]
    chunks = {d.metadata["chunk_id"]: d for d in canonical_documents(data["source"])}
    for case in data["cases"]:
        assert set(case["expected_chunk_ids"]) <= chunks.keys()
        for evidence in case["supporting_evidence"]:
            doc = chunks[evidence["chunk_id"]]
            assert doc.metadata["document_id"] in case["expected_document_ids"]
            assert any(evidence["page"] == span["page_number"]
                       and evidence["quote"] in span["text"]
                       for span in doc.metadata["source_spans"])
            assert "☐" not in evidence["quote"]


def test_conditional_fee_reference_uses_unchanged_calculator_not_assumed_execution():
    cases = {c["id"]: c for c in load_dataset()["cases"]}
    case = cases["Q06"]
    reference = case["conditional_calculation_reference"]
    actual = calculate_late_fee(FeeCalculationInput(**reference["inputs"])).to_dict()
    assert all(actual[k] == v for k, v in reference["result"].items())
    assert case["expected_behavior"] == "clarification"
    assert case["expected_status"] == "needs_clarification"
    assert case["expected_tools"] == ["retrieval"]
    assert case["expected_calculation"] is None
    assert cases["Q07"]["expected_calculation"] is None


@pytest.mark.parametrize("case_id", ["Q06", "Q07"])
def test_fee_clarification_annotations_match_actual_input_requirements(case_id):
    from agent.fee_inputs import extract_fee_input
    data = load_dataset()
    case = next(c for c in data["cases"] if c["id"] == case_id)
    docs = [d for d in canonical_documents(data["source"])
            if d.metadata["chunk_id"] in case["expected_chunk_ids"]]
    inputs, errors = extract_fee_input({
        "question": case["question"], "retrieved_evidence": [{"documents": docs}],
    })
    assert inputs is None
    assert any("payment date" in e for e in errors)
    assert case["expected_calculation"] is None


def test_missing_passwords_have_no_invented_positive_sources():
    data = load_dataset()
    for case in data["cases"][7:9]:
        assert case["expected_status"] == "needs_clarification"
        assert case["expected_document_ids"] == []
        assert case["expected_chunk_ids"] == []
        assert case["supporting_evidence"] == []
        assert case["verification_method"]
    # No assigned network or personal phone password appears in the source.
    import re
    text = "\n".join(d.metadata["source_text"] for d in canonical_documents(data["source"]))
    assert not re.search(r"(?:wi[\s-]?fi|personal phone)\s+password\s*(?:is|:|=)\s*\S+", text, re.I)


def test_maya_is_denied_lease_two_before_retrieval(tmp_path):
    case = load_dataset()["cases"][-1]
    backend = mock_backend(tmp_path)
    with pytest.raises(APIError) as error:
        backend.authorize(case["tenant_id"], case["lease_id"])
    assert error.value.status == 404
    assert case["expected_tools"] == []
    assert case["expected_status"] == "denied"


@pytest.mark.parametrize("change", ["duplicate_id", "missing_field", "missing_evidence", "wrong_status"])
def test_loader_rejects_incomplete_or_contradictory_annotations(tmp_path, change):
    data = deepcopy(load_dataset())
    if change == "duplicate_id":
        data["cases"][1]["id"] = data["cases"][1]["question_id"] = "Q01"
    elif change == "missing_field":
        del data["cases"][0]["expected_key_facts"]
    elif change == "missing_evidence":
        data["cases"][0]["supporting_evidence"] = []
    else:
        data["cases"][0]["expected_status"] = "needs_clarification"
    path = tmp_path / "dataset.json"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        load_dataset(path)

"""Synthetic source policy tests; no real snapshot approval or cloud access."""

from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from laga.rag_configuration import RAGIntegrationError, load_configuration
from laga.rag_integration import ProductionRetrieverFactory, normalize_document
from laga.synthetic_demo import DEMO_NOTICE, MAYA_PDF_SHA256, eligible_status
from lease_rag.chunking import chunk_pdf, extract_document
from lease_rag.manifest import read_manifest
from test_assistant_integration import system, ask, checked
from test_maya_integration_readiness import maya_backend
from test_production_rag import production, write_json


APPROVED = dict(
    enabled=True, organization_id="org-alder-demo", tenant_id="tenant-1",
    tenant_name="Maya Chen", lease_id="lease-1", property_id="property-1",
    backend_document_id="lease-document-1", pinecone_document_id="lease-document-1",
    document_sha256=MAYA_PDF_SHA256,
)


@pytest.fixture
def demo(production, maya_backend, tmp_path):
    """Temporary mock snapshot/bindings only; never installed as real artifacts."""
    p = production
    manifest_path, snapshot_path, bindings_path = (
        tmp_path / "demo-manifest.json", tmp_path / "demo-snapshot.json",
        tmp_path / "demo-bindings.json",
    )
    manifest = json.loads((ROOT / "tests/fixtures/phase6c_documents.json").read_text())
    manifest["documents"][0].update(
        organization_id="org-alder-demo", tenant_id="tenant-1",
        backend_document_id="lease-document-1",
    )
    write_json(manifest_path, manifest)
    record = read_manifest(manifest_path, ROOT / "data")[0]
    chunks, _ = chunk_pdf(record["pdf_path"], record, ROOT / "data")
    selected = next(doc for doc in chunks if (
        "2027-01-31" in doc.metadata["source_text"]
        and 15 in doc.metadata["page_numbers"]
    ))
    snapshot = {
        **p.snapshot, "chunk_count": len(chunks),
        "documents": {"lease-document-1": {"access": "tenant", "tenant_name": "maya chen"}},
    }
    write_json(snapshot_path, snapshot)
    binding = {
        "schema_version": 1,
        "snapshot_sha256": sha256(snapshot_path.read_bytes()).hexdigest(),
        "manifest_sha256": sha256(manifest_path.read_bytes()).hexdigest(),
        "documents": [{
            key: value for key, value in APPROVED.items()
            if key not in {"enabled", "property_id"}
        }],
    }
    write_json(bindings_path, binding)
    config = replace(
        p.config, manifest_path=manifest_path, snapshot_path=snapshot_path,
        bindings_path=bindings_path, data_dir=ROOT / "data", synthetic_demo_enabled=True,
    )
    stats = {"namespaces": {snapshot["namespace"]: {"vector_count": len(chunks)}}}
    p.dense.describe_index_stats.return_value = p.sparse.describe_index_stats.return_value = stats
    p.dense.query.return_value = p.sparse.query.return_value = {"matches": [p.match(selected)]}
    factory = ProductionRetrieverFactory(
        maya_backend, configuration_loader=lambda: config, clients_factory=p.clients,
    )
    old = maya_backend._assistant.retriever_factory
    maya_backend._assistant.retriever_factory = factory
    yield dict(
        p=p, backend=maya_backend, config=config, factory=factory, record=record,
        manifest=manifest, binding=binding, selected=selected,
    )
    maya_backend._assistant.retriever_factory = old


def test_demo_flag_defaults_off_and_is_strict(production):
    assert load_configuration(production.env).synthetic_demo_enabled is False
    assert load_configuration({
        **production.env, "LAGA_RAG_SYNTHETIC_DEMO_ENABLED": "true",
    }).synthetic_demo_enabled is True
    with pytest.raises(RAGIntegrationError):
        load_configuration({**production.env, "LAGA_RAG_SYNTHETIC_DEMO_ENABLED": "maybe"})


def test_demo_flag_does_not_enable_retrieval_alone(production, monkeypatch):
    from laga.rag_integration import production_factory_from_environment
    monkeypatch.setenv("LAGA_RAG_ENV_FILE", production.env["LAGA_RAG_ENV_FILE"])
    monkeypatch.setenv("LAGA_RAG_ENABLED", "false")
    monkeypatch.setenv("LAGA_RAG_SYNTHETIC_DEMO_ENABLED", "true")
    assert production_factory_from_environment(production.system.service) is None


@pytest.mark.parametrize("field", [
    "organization_id", "tenant_id", "tenant_name", "lease_id", "property_id",
    "backend_document_id", "pinecone_document_id", "document_sha256",
])
def test_only_the_exact_explicitly_approved_source_identity_is_eligible(field):
    assert eligible_status("synthetic_unsigned", **APPROVED)
    assert not eligible_status("synthetic_unsigned", **{**APPROVED, field: "different"})


def test_production_status_policy_is_unchanged():
    assert eligible_status("signed", **{**APPROVED, "enabled": False})
    assert not eligible_status("synthetic_unsigned", **{**APPROVED, "enabled": False})
    for status in ["unsigned", "unknown", "unfilled_template", "reference_snapshot"]:
        assert not eligible_status(status, **APPROVED)


def test_signed_production_answer_is_unchanged_even_when_demo_flag_is_on(production):
    p = production
    p.system.service._assistant.retriever_factory = ProductionRetrieverFactory(
        p.system.service,
        configuration_loader=lambda: replace(p.config, synthetic_demo_enabled=True),
        clients_factory=p.clients,
    )
    response = checked(ask(p.system.client()))
    assert response["status"] == "supported"
    assert not response["answer"].startswith(DEMO_NOTICE)


def test_demo_uses_actual_hash_and_preserves_status_and_citations(demo):
    d = demo
    retriever = d["factory"]("tenant-1", "Maya Chen", "lease-1")
    result = retriever.invoke("When does my lease expire?")[0]
    assert result.metadata["document_status"] == "synthetic_unsigned"
    assert result.metadata["document_sha256"] == MAYA_PDF_SHA256
    assert result.metadata["property_id"] == "property-1"
    assert result.metadata["page_numbers"] == d["selected"].metadata["page_numbers"]
    assert 15 in result.metadata["page_numbers"]
    assert result.metadata["source_spans"] == d["selected"].metadata["source_spans"]
    assert retriever.is_synthetic_demo is True
    assert d["p"].dense.query.call_args.kwargs["filter"]["$and"][0] == {
        "document_id": {"$in": ["lease-document-1"]},
    }
    d["p"].pc.create_index.assert_not_called()


def test_backend_demo_answer_visibly_discloses_unsigned_status(demo):
    response = demo["backend"].post_assistant_messages(
        user={"id": "tenant-1"}, question="When does my lease expire?",
        scope={"type": "lease", "id": "lease-1"}, asOf="2026-11-05",
    )
    assert response["answer"].startswith(DEMO_NOTICE)
    assert response["status"] == "supported"
    assert response["citations"][0]["documentId"] == "lease-document-1"
    assert response["compliance"] == {"status": "unavailable"}


@pytest.mark.parametrize("change", ["disabled", "wrong_hash", "wrong_property", "missing_snapshot", "pending"])
def test_demo_never_bypasses_other_approval_gates(demo, change):
    d, p = demo, demo["p"]
    config = d["config"]
    if change == "disabled":
        config = replace(config, synthetic_demo_enabled=False)
    elif change == "missing_snapshot":
        config.snapshot_path.unlink()
    elif change == "pending":
        write_json(config.bindings_path, {
            "approval_status": "pending", "binding_candidate": d["binding"],
        })
    elif change == "wrong_hash":
        d["binding"]["documents"][0]["document_sha256"] = "0" * 64
        write_json(config.bindings_path, d["binding"])
    elif change == "wrong_property":
        d["manifest"]["documents"][0]["property_id"] = "property-2"
        write_json(config.manifest_path, d["manifest"])
        d["binding"]["manifest_sha256"] = sha256(config.manifest_path.read_bytes()).hexdigest()
        write_json(config.bindings_path, d["binding"])
    factory = ProductionRetrieverFactory(
        d["backend"], configuration_loader=lambda: config, clients_factory=p.clients,
    )
    with pytest.raises(RAGIntegrationError):
        factory("tenant-1", "Maya Chen", "lease-1")
    p.clients.assert_not_called()


def test_cross_tenant_access_stays_rejected_in_demo_mode(demo):
    with pytest.raises(RAGIntegrationError):
        demo["factory"]("tenant-2", "James Wilson", "lease-1")
    demo["p"].clients.assert_not_called()


def test_demo_rejects_forged_status_or_source(demo):
    from copy import deepcopy
    retriever = demo["factory"]("tenant-1", "Maya Chen", "lease-1")
    for field, value in [("document_status", "signed"), ("source_text", "forged")]:
        document = deepcopy(demo["selected"])
        document.metadata[field] = value
        with pytest.raises(RAGIntegrationError):
            normalize_document(document, retriever.scope)


def test_page_three_pet_span_is_only_provenance_not_additional_terms():
    record = read_manifest(ROOT / "documents.example.json", ROOT / "data")[0]
    chunks, _ = chunk_pdf(record["pdf_path"], record, ROOT / "data")
    pet = next(doc for doc in chunks if doc.metadata["section_id"] == "11")
    extracted = extract_document(record["pdf_path"], record, ROOT / "data")
    for span in pet.metadata["source_spans"]:
        page = extracted["pages"][span["page_number"] - 1]
        assert page["text"][span["char_start"]:span["char_end"]] == span["text"]
    page_three = [s["text"] for s in pet.metadata["source_spans"] if s["page_number"] == 3]
    assert page_three == ["SYNTHETIC / UNSIGNED TEST DATA - Maya Chen - lease-document-1"]
    assert "$250.00" in pet.metadata["source_spans"][0]["text"]
    assert pet.metadata["has_unfilled_fields"] is False

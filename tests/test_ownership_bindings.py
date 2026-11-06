"""Independent backend ownership bindings; no live services or operational files."""

from copy import deepcopy
from dataclasses import replace
from hashlib import sha256

import pytest

from laga.rag_configuration import RAGIntegrationError
from laga.rag_mapping import verify_scope
from test_synthetic_demo import demo, production, maya_backend, system
from test_production_rag import write_json


@pytest.fixture
def independent_binding(demo):
    """Use canonical ingestion without invented backend-only metadata."""
    config = demo["config"]
    for row in demo["manifest"]["documents"]:
        for key in ("organization_id", "tenant_id", "backend_document_id"):
            row.pop(key, None)
    write_json(config.manifest_path, demo["manifest"])
    demo["binding"]["manifest_sha256"] = sha256(config.manifest_path.read_bytes()).hexdigest()
    write_json(config.bindings_path, demo["binding"])
    return demo


def scope(d):
    return verify_scope(d["backend"], d["config"], "tenant-1", "Maya Chen", "lease-1")


def test_maya_binding_uses_sqlite_without_mutating_canonical_inputs(independent_binding):
    d = independent_binding
    paths = (d["config"].manifest_path, d["config"].snapshot_path)
    before = [p.read_bytes() for p in paths]
    result = scope(d)
    assert result.organization_id == "org-alder-demo"
    assert result.property_id == "property-1"
    assert result.backend_document_ids == frozenset({"lease-document-1"})
    assert result.synthetic_document_ids == frozenset({"lease-document-1"})
    assert [p.read_bytes() for p in paths] == before
    d["p"].clients.assert_not_called()


@pytest.mark.parametrize("field,value", [
    ("tenant_id", "tenant-2"), ("tenant_name", "James Wilson"),
    ("organization_id", "wrong-org"), ("lease_id", "lease-2"),
    ("backend_document_id", "wrong-backend"),
    ("pinecone_document_id", "wrong-pinecone"), ("document_sha256", "0" * 64),
])
def test_wrong_binding_identity_rejected(independent_binding, field, value):
    d = independent_binding
    d["binding"]["documents"][0][field] = value
    write_json(d["config"].bindings_path, d["binding"])
    with pytest.raises(RAGIntegrationError):
        scope(d)
    d["p"].clients.assert_not_called()


@pytest.mark.parametrize("field", [
    "organization_id", "tenant_id", "backend_document_id", "lease_id", "property_id",
])
def test_explicit_manifest_conflicts_still_rejected(independent_binding, field):
    d = independent_binding
    d["manifest"]["documents"][0][field] = "conflicting"
    write_json(d["config"].manifest_path, d["manifest"])
    d["binding"]["manifest_sha256"] = sha256(d["config"].manifest_path.read_bytes()).hexdigest()
    write_json(d["config"].bindings_path, d["binding"])
    with pytest.raises(RAGIntegrationError):
        scope(d)


@pytest.mark.parametrize("change", [
    "manifest", "snapshot", "missing_binding", "duplicate_binding", "demo_disabled",
])
def test_provenance_and_demo_gates_remain_mandatory(independent_binding, change):
    d = independent_binding
    config = d["config"]
    if change in ("manifest", "snapshot"):
        path = getattr(config, change + "_path")
        path.write_bytes(path.read_bytes() + b"\n")
    elif change == "missing_binding":
        config.bindings_path.unlink()
    elif change == "duplicate_binding":
        d["binding"]["documents"].append(deepcopy(d["binding"]["documents"][0]))
        write_json(config.bindings_path, d["binding"])
    else:
        d["config"] = replace(config, synthetic_demo_enabled=False)
    with pytest.raises(RAGIntegrationError):
        scope(d)
    d["p"].clients.assert_not_called()


def test_cross_tenant_caller_cannot_use_approved_mapping(independent_binding):
    d = independent_binding
    with pytest.raises(RAGIntegrationError):
        verify_scope(d["backend"], d["config"], "tenant-2", "James Wilson", "lease-1")

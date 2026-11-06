"""Offline preparation checks, not approval to retrieve unsigned contracts.

The manifest fixture is an exact upstream snapshot, so tests remain portable
without the ignored operator documents.json or a network/Git dependency.
"""

from contextlib import closing
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import sys
from unittest.mock import Mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from laga.backend_api import APIError, BackendAPI
from laga.bootstrap import bootstrap_database
from laga.rag_configuration import RAGIntegrationError, load_configuration
from laga.rag_integration import ProductionRetrieverFactory
from test_assistant_integration import system, ask, checked
from test_production_rag import production, write_json


MANIFEST = ROOT / "tests/fixtures/phase6c_documents.json"
MANIFEST_SHA256 = "52e07f6d3264103136c61c3c5faf8b328ac1bd955cb074ddd4e4e3c2c299dafa"
UPSTREAM_PDF_SHA256 = "4a8c24f993152af5f4a61da328b3fcdf0932e2438114b20b343c5ef1d11dbf55"


@pytest.fixture(scope="module")
def maya_backend(tmp_path_factory):
    directory = tmp_path_factory.mktemp("maya-readiness")
    backend = BackendAPI(
        directory / "backend.sqlite3", assistant_retriever_factory=Mock(),
    )
    # Seed a disposable database only, never the running workspace database.
    bootstrap_database(backend, credentials_path=directory / "test-login.json")
    return backend


def maya_record():
    records = json.loads(MANIFEST.read_text())["documents"]
    return next(row for row in records if row["document_id"] == "lease-document-1")


def test_manifest_fixture_is_exact_reviewed_upstream_snapshot():
    assert sha256(MANIFEST.read_bytes()).hexdigest() == MANIFEST_SHA256
    row = maya_record()
    assert row["tenant_name"] == "Maya Chen"
    assert row["lease_id"] == "lease-1"
    assert row["property_id"] == "property-1"
    assert row["document_status"] == "synthetic_unsigned"


def test_maya_mapping_matches_bootstrap_and_disposable_sqlite(maya_backend):
    fixture = json.loads((ROOT / "contracts/bootstrap.json").read_text())
    expected = next(row for row in fixture["leases"] if row["lease"]["id"] == "lease-1")["lease"]
    with closing(maya_backend._connect()) as db:
        user, org = maya_backend._principal(
            db, {"id": "tenant-1"}, role="tenant", permission="lease:read",
        )
        lease, _ = maya_backend._lease(db, org, user, "lease-1")
    assert user["name"] == "Maya Chen"
    assert org == fixture["organizationId"]
    assert lease == expected
    assert lease["tenantId"] == "tenant-1"
    assert lease["propertyId"] == maya_record()["property_id"]


def test_lease_and_document_ids_are_distinct_and_resolve_explicitly(maya_backend):
    row = maya_record()
    with closing(maya_backend._connect()) as db:
        user, org = maya_backend._principal(db, {"id": "tenant-1"})
        lease, _ = maya_backend._lease(db, org, user, row["lease_id"])
    assert row["lease_id"] != row["document_id"]
    assert lease["documents"] == [row["document_id"]]
    assert row["path"] == "Free-North-Carolina-Standard-Lease-Agreement-Template.pdf"


def test_other_tenant_cannot_resolve_maya_lease_or_initialize_retrieval(maya_backend):
    with closing(maya_backend._connect()) as db:
        user, org = maya_backend._principal(db, {"id": "tenant-2"})
        with pytest.raises(APIError) as error:
            maya_backend._lease(db, org, user, "lease-1")
    assert error.value.status == 404
    loader, clients = Mock(), Mock()
    factory = ProductionRetrieverFactory(
        maya_backend, configuration_loader=loader, clients_factory=clients,
    )
    with pytest.raises(RAGIntegrationError):
        factory("tenant-2", user["name"], "lease-1")
    loader.assert_not_called()
    clients.assert_not_called()


def test_maya_missing_snapshot_fails_before_cloud_or_binding_approval(maya_backend, production, tmp_path):
    clients = Mock()
    config = replace(production.config, snapshot_path=tmp_path / "missing-active.json")
    factory = ProductionRetrieverFactory(
        maya_backend, configuration_loader=lambda: config, clients_factory=clients,
    )
    with pytest.raises(RAGIntegrationError) as error:
        factory("tenant-1", "Maya Chen", "lease-1")
    assert error.value.code == "RAG_UNAVAILABLE"
    clients.assert_not_called()


@pytest.mark.parametrize("key", ["PINECONE_API_KEY", "NEBIUS_API_KEY"])
def test_maya_missing_credentials_fail_without_using_cloud(maya_backend, production, key):
    env = {**production.env, key: ""}
    clients = Mock()
    factory = ProductionRetrieverFactory(
        maya_backend, configuration_loader=lambda: load_configuration(env),
        clients_factory=clients,
    )
    with pytest.raises(RAGIntegrationError) as error:
        factory("tenant-1", "Maya Chen", "lease-1")
    assert error.value.code == "RAG_CONFIGURATION_ERROR"
    clients.assert_not_called()


def test_binding_for_different_pdf_hash_is_rejected(production):
    # The actual upstream Maya hash cannot approve a different PDF's bytes.
    # This deliberately uses the isolated Phase 6B signed test control, so the
    # hash check is exercised rather than short-circuited by unsigned status.
    p = production
    p.binding["documents"][0]["document_sha256"] = UPSTREAM_PDF_SHA256
    write_json(p.bindings_path, p.binding)
    assert checked(ask(p.system.client()), 503)["code"] == "RAG_MAPPING_INVALID"
    p.clients.assert_not_called()


def test_synthetic_unsigned_status_stays_rejected_even_with_pinned_inputs(production):
    p = production
    p.manifest[0]["document_status"] = maya_record()["document_status"]
    write_json(p.manifest_path, {"documents": p.manifest})
    p.binding["manifest_sha256"] = sha256(p.manifest_path.read_bytes()).hexdigest()
    write_json(p.bindings_path, p.binding)
    assert checked(ask(p.system.client()), 503)["code"] == "RAG_MAPPING_INVALID"
    p.clients.assert_not_called()

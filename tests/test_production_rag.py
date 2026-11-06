"""Isolated production-adapter tests: real hybrid code, fake cloud clients.

These tests do not verify live Pinecone or real credentials.
"""

from copy import deepcopy
from hashlib import sha256
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject

from test_assistant_integration import system, ask, checked, FEE_QUESTION
from laga.backend_api import BackendAPI
from laga.rag_configuration import (
    RAGIntegrationError, activation_requested, load_configuration, runtime_values,
)
from laga.rag_integration import ProductionRetrieverFactory, normalize_document
from lease_rag.chunking import chunk_pdf
from lease_rag.manifest import read_manifest
from lease_rag.storage import pinecone_metadata


def write_pdf(path, pages):
    writer = PdfWriter()
    for lines in pages:
        page = writer.add_blank_page(width=612, height=792)
        font = DictionaryObject({
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        })
        page[NameObject("/Resources")] = DictionaryObject({
            NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)}),
        })
        commands = ["BT /F1 11 Tf 50 740 Td"]
        for line in lines:
            escaped = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            commands.append(f"({escaped}) Tj 0 -18 Td")
        commands.append("ET")
        stream = DecodedStreamObject()
        stream.set_data("\n".join(commands).encode("latin-1"))
        page[NameObject("/Contents")] = writer._add_object(stream)
    writer.write(path)


def write_json(path, data):
    path.write_text(json.dumps(data, sort_keys=True), encoding="utf-8")


@pytest.fixture
def production(system, tmp_path):
    data = tmp_path / "pdfs"
    data.mkdir()
    write_pdf(data / "a.pdf", [
        ["3. RENT.", "Monthly rent is $1,000.00. A flat late fee of $20.00 applies."],
        ["Pets are allowed with prior written approval and no additional pet fee."],
    ])
    write_pdf(data / "b.pdf", [["3. RENT.", "PRIVATE TENANT B has monthly rent of $9,999.00."]])
    write_pdf(data / "NC_general_statutes_Chapter_42.pdf", [
        ["Article 1.", "Reference only", "This shared statute is not a signed lease term."],
    ])
    rows = []
    for key in ("a", "b"):
        rows.append({
            "path": f"{key}.pdf", "document_id": f"pinecone-{key}",
            "tenant_name": f"Tenant {key.upper()}", "tenant_id": f"tenant-{key}",
            "organization_id": "org-a", "lease_id": f"lease-{key}",
            "backend_document_id": f"document-{key}", "access": "tenant",
            "document_type": "lease", "document_status": "signed",
            "document_title": f"Synthetic signed test lease {key}",
        })
    rows.append({
        "path": "NC_general_statutes_Chapter_42.pdf", "document_id": "nc-law",
        "access": "shared", "document_title": "Synthetic shared reference",
    })
    manifest_path, snapshot_path, bindings_path = (
        tmp_path / "documents.json", tmp_path / "active.json", tmp_path / "rag_bindings.json",
    )
    empty_env = tmp_path / "local.env"
    empty_env.write_text("")
    env = {
        "LAGA_RAG_ENABLED": "true", "LAGA_RAG_ENV_FILE": str(empty_env),
        "LAGA_RAG_MANIFEST_FILE": str(manifest_path),
        "LAGA_RAG_SNAPSHOT_FILE": str(snapshot_path),
        "LAGA_RAG_BINDINGS_FILE": str(bindings_path), "LAGA_RAG_DATA_DIR": str(data),
        "PINECONE_INDEX_NAME": "laga-test-dense", "PINECONE_SPARSE_INDEX_NAME": "laga-test-sparse",
        "PINECONE_API_KEY": "isolated-test-key", "NEBIUS_API_KEY": "isolated-test-key",
    }
    config = load_configuration(env)
    write_json(manifest_path, {"documents": rows})
    records = read_manifest(manifest_path, data)
    documents = [
        chunk for record in records
        for chunk in chunk_pdf(record["pdf_path"], record, data)[0]
    ]
    assert len(documents) == 3
    snapshot = {
        "schema_version": 1, "profile": config.settings.profile,
        "dense_index": config.settings.dense_index_name,
        "sparse_index": config.settings.sparse_index_name,
        "namespace": "leases-v1-" + "a" * 24, "chunk_count": len(documents),
        "documents": {
            doc.metadata["document_id"]: {
                "access": doc.metadata["access"], "tenant_name": doc.metadata["tenant_name"],
            } for doc in documents
        },
    }
    write_json(snapshot_path, snapshot)
    binding = {
        "schema_version": 1,
        "snapshot_sha256": sha256(snapshot_path.read_bytes()).hexdigest(),
        "manifest_sha256": sha256(manifest_path.read_bytes()).hexdigest(),
        "documents": [{
            "organization_id": "org-a", "tenant_id": "tenant-a", "tenant_name": "Tenant A",
            "lease_id": "lease-a", "backend_document_id": "document-a",
            "pinecone_document_id": "pinecone-a",
            "document_sha256": sha256((data / "a.pdf").read_bytes()).hexdigest(),
        }],
    }
    write_json(bindings_path, binding)

    def match(doc):
        return {"id": doc.metadata["chunk_id"], "metadata": pinecone_metadata(doc), "score": 0.9}

    stats = {"namespaces": {snapshot["namespace"]: {"vector_count": len(documents)}}}
    dense = SimpleNamespace(
        query=Mock(return_value={"matches": [match(documents[0])]}),
        describe_index_stats=Mock(return_value=deepcopy(stats)),
    )
    sparse = SimpleNamespace(
        query=Mock(return_value={"matches": [match(documents[0])]}),
        describe_index_stats=Mock(return_value=deepcopy(stats)),
    )
    def description(name):
        is_sparse = name == config.settings.sparse_index_name
        return {
            "name": name, "metric": "dotproduct" if is_sparse else "cosine",
            "vector_type": "sparse" if is_sparse else "dense",
            "dimension": None if is_sparse else 4096,
            "host": name + ".pinecone.test", "status": {"ready": True},
        }
    pc = SimpleNamespace(
        describe_index=Mock(side_effect=description),
        Index=Mock(side_effect=lambda *, host: sparse if "sparse" in host else dense),
        inference=SimpleNamespace(embed=Mock(side_effect=lambda **kwargs: [
            {"sparse_indices": [1], "sparse_values": [0.5]} for _ in kwargs["inputs"]
        ])),
        create_index=Mock(side_effect=AssertionError("Production adapter must never create indexes")),
    )
    embeddings = SimpleNamespace(embed_query=Mock(return_value=[1.0, 0.0]))
    clients = Mock(return_value=(pc, embeddings))
    factory = ProductionRetrieverFactory(
        system.service, configuration_loader=lambda: load_configuration(env), clients_factory=clients,
    )
    system.service._assistant.retriever_factory = factory
    yield SimpleNamespace(
        system=system, factory=factory, config=config, env=env, binding=binding,
        snapshot=snapshot, manifest=rows, documents=documents, data=data,
        bindings_path=bindings_path, snapshot_path=snapshot_path, manifest_path=manifest_path,
        dense=dense, sparse=sparse, pc=pc, clients=clients, embeddings=embeddings, match=match,
    )


def test_authorized_backend_runs_real_hybrid_graph_and_preserves_original_document_id(production):
    p = production
    answer = checked(ask(p.system.client()))
    assert answer["status"] == "supported"
    assert answer["citations"][0]["documentId"] == "pinecone-a"
    assert answer["citations"][0]["section"] == "3 — RENT"
    assert answer["citations"][0]["page"] == 2
    assert "PRIVATE TENANT B" not in answer["answer"]
    assert answer["compliance"] == {"status": "unavailable"}
    p.pc.create_index.assert_not_called()
    assert p.pc.describe_index.call_count == 2


def test_factory_interface_and_evidence_metadata_fidelity(production):
    p = production
    retriever = p.factory("tenant-a", "Tenant A", "lease-a")
    doc = retriever.invoke("Pets?")[0]
    original = p.documents[0]
    for field in [
        "document_id", "chunk_id", "page_numbers", "section_id", "clause_id",
        "citation_label", "source_text", "source_spans",
    ]:
        assert doc.metadata[field] == original.metadata[field]
    assert doc.metadata["page_numbers"] == [1, 2]
    assert doc.metadata["clause_id"] is None
    assert "page_number" not in doc.metadata
    assert doc.metadata["tenant_id"] == "tenant-a"
    assert doc.metadata["organization_id"] == "org-a"
    assert doc.metadata["lease_id"] == "lease-a"
    assert doc.metadata["backend_document_id"] == "document-a"
    assert doc.page_content == original.metadata["source_text"]


def test_dense_and_sparse_filters_are_same_explicit_lease_scope_without_shared_law(production):
    p = production
    checked(ask(p.system.client(), question="What is my rent and what are my pet rules?"))
    dense_filter = p.dense.query.call_args.kwargs["filter"]
    assert dense_filter == p.sparse.query.call_args.kwargs["filter"]
    assert dense_filter["$and"][0] == {"document_id": {"$in": ["pinecone-a"]}}
    assert dense_filter["$and"][1]["$or"][0]["$and"][1] == {"tenant_name": {"$eq": "tenant a"}}
    assert p.dense.query.call_args.kwargs["namespace"] == p.snapshot["namespace"]
    assert p.sparse.query.call_args.kwargs["namespace"] == p.snapshot["namespace"]
    assert "pinecone-b" not in json.dumps(dense_filter)
    assert "nc-law" not in json.dumps(dense_filter)


def test_fee_calculation_with_canonical_verified_pdf_evidence(production):
    answer = checked(ask(production.system.client(), question=FEE_QUESTION))
    assert answer["status"] == "supported"
    assert answer["calculations"][0]["result"] == 2000
    assert answer["calculations"][0]["inputs"]["statutory_maximum_usd"] == "50.00"


def test_cross_tenant_backend_and_direct_factory_fail_before_cloud_initialization(production):
    p = production
    checked(ask(p.system.client("b")), 404)
    with pytest.raises(RAGIntegrationError):
        p.factory("tenant-b", "Tenant B", "lease-a")
    with pytest.raises(RAGIntegrationError):
        p.factory("tenant-a", "Tenant B", "lease-a")
    p.clients.assert_not_called()


@pytest.mark.parametrize(("field", "value"), [
    ("tenant_id", "tenant-b"), ("tenant_name", "Tenant B"), ("lease_id", "lease-b"),
    ("organization_id", "org-b"), ("backend_document_id", "document-b"),
    ("pinecone_document_id", "pinecone-b"), ("document_sha256", "0" * 64),
])
def test_incorrect_mapping_fails_closed_without_cloud_calls(production, field, value):
    p = production
    p.binding["documents"][0][field] = value
    write_json(p.bindings_path, p.binding)
    error = checked(ask(p.system.client()), 503)
    assert error["code"] == "RAG_MAPPING_INVALID"
    p.clients.assert_not_called()


@pytest.mark.parametrize("missing", ["snapshot", "bindings", "manifest"])
def test_missing_ingestion_inputs_fail_closed(production, missing):
    p = production
    getattr(p, missing + "_path").unlink()
    error = checked(ask(p.system.client()), 503)
    assert error["code"] == ("RAG_UNAVAILABLE" if missing == "snapshot" else "RAG_MAPPING_INVALID")
    p.clients.assert_not_called()


@pytest.mark.parametrize("field", ["snapshot_sha256", "manifest_sha256"])
def test_snapshot_and_manifest_require_explicit_operator_hash_pins(production, field):
    p = production
    p.binding[field] = "0" * 64
    write_json(p.bindings_path, p.binding)
    assert checked(ask(p.system.client()), 503)["code"] == "RAG_MAPPING_INVALID"
    p.clients.assert_not_called()


def test_duplicate_document_ownership_is_rejected(production):
    p = production
    p.binding["documents"].append(deepcopy(p.binding["documents"][0]))
    write_json(p.bindings_path, p.binding)
    assert checked(ask(p.system.client()), 503)["code"] == "RAG_MAPPING_INVALID"
    p.clients.assert_not_called()


def test_manifest_without_canonical_lease_identity_cannot_be_enabled_by_hash_alone(production):
    p = production
    del p.manifest[0]["lease_id"]
    write_json(p.manifest_path, {"documents": p.manifest})
    p.binding["manifest_sha256"] = sha256(p.manifest_path.read_bytes()).hexdigest()
    write_json(p.bindings_path, p.binding)
    assert checked(ask(p.system.client()), 503)["code"] == "RAG_MAPPING_INVALID"
    p.clients.assert_not_called()


@pytest.mark.parametrize(("field", "value"), [
    ("document_status", "unfilled_template"), ("document_type", "lease_template"),
])
def test_templates_and_unsigned_documents_fail_preflight_before_cloud(production, field, value):
    p = production
    p.manifest[0][field] = value
    write_json(p.manifest_path, {"documents": p.manifest})
    p.binding["manifest_sha256"] = sha256(p.manifest_path.read_bytes()).hexdigest()
    write_json(p.bindings_path, p.binding)
    assert checked(ask(p.system.client()), 503)["code"] == "RAG_MAPPING_INVALID"
    p.clients.assert_not_called()


@pytest.mark.parametrize("field", ["profile", "namespace", "dense_index", "sparse_index"])
def test_snapshot_profile_index_and_namespace_mismatch_reject_before_cloud(production, field):
    p = production
    p.snapshot[field] = {} if field == "profile" else "wrong"
    write_json(p.snapshot_path, p.snapshot)
    assert checked(ask(p.system.client()), 503)["code"] == "RAG_CONFIGURATION_ERROR"
    p.clients.assert_not_called()


@pytest.mark.parametrize("field", ["dimension", "metric", "vector_type", "status", "name"])
def test_existing_index_schema_is_verified_without_creating_or_reconfiguring(production, field):
    p = production
    original = p.pc.describe_index.side_effect
    def invalid(name):
        result = original(name)
        result[field] = {"ready": False} if field == "status" else "wrong"
        return result
    p.pc.describe_index.side_effect = invalid
    assert checked(ask(p.system.client()), 503)["code"] == "RAG_CONFIGURATION_ERROR"
    p.pc.create_index.assert_not_called()
    p.dense.query.assert_not_called()


def test_missing_or_incomplete_cloud_namespace_is_not_queried(production):
    p = production
    p.dense.describe_index_stats.return_value = {"namespaces": {}}
    assert checked(ask(p.system.client()), 503)["code"] == "RAG_CONFIGURATION_ERROR"
    p.dense.query.assert_not_called()


@pytest.mark.parametrize("stage", ["clients", "describe", "dense_query", "sparse_query"])
def test_pinecone_failures_are_safe_errors_not_silent_abstention_or_mock_fallback(production, stage):
    p = production
    target = {
        "clients": p.clients, "describe": p.pc.describe_index,
        "dense_query": p.dense.query, "sparse_query": p.sparse.query,
    }[stage]
    target.side_effect = RuntimeError("PRIVATE_PROVIDER_TOKEN_AND_PATH")
    response = ask(p.system.client())
    assert checked(response, 503)["code"] == "RAG_UNAVAILABLE"
    assert "PRIVATE_PROVIDER_TOKEN_AND_PATH" not in response.text


@pytest.mark.parametrize("foreign_index", [1, 2])
def test_foreign_tenant_or_shared_statute_cannot_become_lease_evidence(production, foreign_index):
    p = production
    p.dense.query.return_value = {"matches": [p.match(p.documents[foreign_index])]}
    response = ask(p.system.client())
    assert checked(response, 503)["code"] == "RAG_EVIDENCE_INVALID"
    assert "PRIVATE TENANT B" not in response.text
    assert "not a signed lease" not in response.text


@pytest.mark.parametrize("field", ["source_text", "source_spans", "page_numbers", "section_id", "chunk_id"])
def test_corrupted_source_metadata_is_rejected_against_local_canonical_chunks(production, field):
    p = production
    altered = deepcopy(p.documents[0])
    replacement = {
        "source_text": "PRIVATE FOREIGN TEXT", "source_spans": [],
        "page_numbers": [99], "section_id": "99", "chunk_id": "foreign-chunk",
    }
    altered.metadata[field] = replacement[field]
    p.dense.query.return_value = p.sparse.query.return_value = {"matches": [p.match(altered)]}
    assert checked(ask(p.system.client()), 503)["code"] == "RAG_EVIDENCE_INVALID"


def test_correct_identity_labels_cannot_hide_a_corrupted_stored_chunk_body(production):
    p = production
    forged = deepcopy(p.documents[0])
    forged.page_content = "PRIVATE TENANT B"
    p.dense.query.return_value = p.sparse.query.return_value = {"matches": [p.match(forged)]}
    response = ask(p.system.client())
    assert checked(response, 503)["code"] == "RAG_EVIDENCE_INVALID"
    assert "PRIVATE TENANT B" not in response.text


def test_successful_graph_retry_does_not_hide_a_production_retrieval_failure(production):
    p = production
    p.dense.query.side_effect = [
        RuntimeError("transient provider failure"), {"matches": [p.match(p.documents[0])]},
    ]
    assert checked(ask(p.system.client()), 503)["code"] == "RAG_UNAVAILABLE"
    assert p.dense.query.call_count == 2


def test_environment_can_activate_factory_without_backend_or_question_identity_overrides(production, monkeypatch):
    p = production
    for key, value in p.env.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr("lease_rag.config.Settings.clients", lambda settings: (p.pc, p.embeddings))
    backend = BackendAPI(p.system.service.database)
    assert isinstance(backend._assistant.retriever_factory, ProductionRetrieverFactory)
    answer = checked(ask(p.system.client(backend=backend)))
    assert answer["status"] == "supported"
    assert answer["citations"][0]["documentId"] == "pinecone-a"


def test_unconfigured_backend_keeps_rag_unavailable_behavior(production, monkeypatch):
    p = production
    monkeypatch.setenv("LAGA_RAG_ENABLED", "false")
    monkeypatch.setenv("LAGA_RAG_ENV_FILE", p.env["LAGA_RAG_ENV_FILE"])
    backend = BackendAPI(p.system.service.database)
    assert backend._assistant.retriever_factory is None
    assert checked(ask(p.system.client(backend=backend)), 503)["code"] == "RAG_UNAVAILABLE"
    p.clients.assert_not_called()


def test_local_dotenv_support_environment_precedence_and_secret_repr(production):
    p = production
    local = p.data.parent / "settings.env"
    local.write_text("LAGA_RAG_ENABLED=true\nPINECONE_API_KEY=local-test-only\n")
    env = {**p.env, "LAGA_RAG_ENV_FILE": str(local), "PINECONE_API_KEY": "environment-test-only"}
    values = runtime_values(env)
    assert values["PINECONE_API_KEY"] == "environment-test-only"
    config = load_configuration(env)
    assert "environment-test-only" not in repr(config)
    assert "environment-test-only" not in repr(config.settings)
    del env["PINECONE_API_KEY"]
    assert load_configuration(env).settings.require("PINECONE_API_KEY") == "local-test-only"


@pytest.mark.parametrize(("key", "value"), [
    ("PINECONE_INDEX_NAME", "Bad/INDEX"), ("PINECONE_SPARSE_INDEX_NAME", "laga-test-dense"),
    ("PINECONE_API_KEY", ""), ("NEBIUS_API_KEY", ""), ("LAGA_RAG_ENABLED", "maybe"),
])
def test_bad_settings_are_rejected_without_exposing_values(production, key, value):
    env = {**production.env, key: value}
    with pytest.raises(RAGIntegrationError) as error:
        load_configuration(env)
    assert error.value.code == "RAG_CONFIGURATION_ERROR"
    assert "isolated-test-key" not in str(error.value)


def test_disabled_environment_flag_overrides_local_activation(production, monkeypatch):
    p = production
    local = p.data.parent / "activate.env"
    local.write_text("LAGA_RAG_ENABLED=true\n")
    monkeypatch.setenv("LAGA_RAG_ENV_FILE", str(local))
    monkeypatch.setenv("LAGA_RAG_ENABLED", "false")
    assert activation_requested() is False
    local.unlink()
    assert activation_requested() is False

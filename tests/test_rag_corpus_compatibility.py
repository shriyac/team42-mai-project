"""Upstream-format compatibility with isolated fake SDKs; never live approval."""

from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
import sys
from unittest.mock import Mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from laga.rag_configuration import RAGIntegrationError, load_configuration
from laga.rag_integration import ProductionRetrieverFactory
from lease_rag.config import fingerprint
from lease_rag.storage import pinecone_metadata
from test_assistant_integration import system, ask, checked
from test_production_rag import production, write_json
from test_synthetic_demo import demo
from test_maya_integration_readiness import maya_backend


def pin_mock_corpus(p, *, namespace="team-shared-namespace"):
    """Derive fake corpus from real fixture chunks exactly as upstream does."""
    corpus = fingerprint({
        "profile": p.config.settings.profile,
        "documents": sorted(
            (doc.metadata["chunk_id"], pinecone_metadata(doc)) for doc in p.documents
        ),
    })
    p.snapshot.update(corpus_id=corpus, namespace=namespace)
    write_json(p.snapshot_path, p.snapshot)
    p.binding["snapshot_sha256"] = sha256(p.snapshot_path.read_bytes()).hexdigest()
    write_json(p.bindings_path, p.binding)
    p.env["PINECONE_NAMESPACE"] = namespace
    records = {}
    for original in p.documents:
        doc = deepcopy(original)
        record_id = doc.metadata["chunk_id"] + ":" + corpus[:24]
        doc.metadata.update(corpus_id=corpus, record_id=record_id)
        flat = pinecone_metadata(doc)
        flat.update(corpus_id=corpus, record_id=record_id)
        records[record_id] = dict(id=record_id, metadata=flat, score=0.9)
    for index in (p.dense, p.sparse):
        index.fetch = Mock(side_effect=lambda *, ids, namespace: {
            "vectors": {key: deepcopy(records[key]) for key in ids if key in records},
        })
        index.describe_index_stats.return_value = {
            "namespaces": {namespace: {"vector_count": len(p.documents) * 3}},
        }
        first = p.documents[0].metadata["chunk_id"] + ":" + corpus[:24]
        index.query.return_value = {"matches": [deepcopy(records[first])]}
    return records


def test_reused_namespace_with_old_versions_has_exact_records_and_scoped_filters(production):
    p = production
    records = pin_mock_corpus(p)
    answer = checked(ask(p.system.client()))
    assert answer["status"] == "supported"
    assert answer["citations"][0]["documentId"] == "pinecone-a"
    for index in (p.dense, p.sparse):
        index.fetch.assert_called_once()
        ids = index.fetch.call_args.kwargs["ids"]
        assert len(ids) == 1 and ids[0] in records
        query = index.query.call_args.kwargs
        assert query["namespace"] == p.env["PINECONE_NAMESPACE"]
        assert {"corpus_id": {"$eq": p.snapshot["corpus_id"]}} in query["filter"]["$and"]
        assert query["filter"]["$and"][0] == {"document_id": {"$in": ["pinecone-a"]}}
    p.pc.create_index.assert_not_called()


def test_generated_namespace_without_override_is_supported(production):
    p = production
    pin_mock_corpus(p)
    pin_mock_corpus(p, namespace="leases-v1-" + p.snapshot["corpus_id"][:24])
    del p.env["PINECONE_NAMESPACE"]
    assert checked(ask(p.system.client()))["status"] == "supported"


@pytest.mark.parametrize("index_name", ["dense", "sparse"])
def test_high_namespace_total_cannot_hide_missing_authorized_active_records(production, index_name):
    p = production
    pin_mock_corpus(p)
    getattr(p, index_name).fetch.return_value = {"vectors": {}}
    getattr(p, index_name).fetch.side_effect = None
    assert checked(ask(p.system.client()), 503)["code"] == "RAG_CONFIGURATION_ERROR"
    p.dense.query.assert_not_called()
    p.sparse.query.assert_not_called()


@pytest.mark.parametrize("field", ["corpus_id", "record_id", "text", "evidence_json"])
def test_fetched_record_corruption_rejects_before_queries(production, field):
    p = production
    pin_mock_corpus(p)
    original = p.sparse.fetch.side_effect
    def corrupt(**kwargs):
        result = original(**kwargs)
        next(iter(result["vectors"].values()))["metadata"][field] = "corrupt"
        return result
    p.sparse.fetch.side_effect = corrupt
    assert checked(ask(p.system.client()), 503)["code"] == "RAG_EVIDENCE_INVALID"
    p.dense.query.assert_not_called()


@pytest.mark.parametrize("field", ["corpus_id", "chunk_count", "documents"])
def test_pinned_but_inconsistent_corpus_fails_before_clients(production, field):
    p = production
    pin_mock_corpus(p)
    p.snapshot[field] = {
        "corpus_id": "0" * 64, "chunk_count": 999, "documents": {"fake": {}},
    }[field]
    write_json(p.snapshot_path, p.snapshot)
    p.binding["snapshot_sha256"] = sha256(p.snapshot_path.read_bytes()).hexdigest()
    write_json(p.bindings_path, p.binding)
    assert checked(ask(p.system.client()), 503)["code"] == "RAG_MAPPING_INVALID"
    p.clients.assert_not_called()


def test_namespace_override_must_match_pinned_snapshot(production):
    p = production
    pin_mock_corpus(p)
    p.env["PINECONE_NAMESPACE"] = "different"
    assert checked(ask(p.system.client()), 503)["code"] == "RAG_CONFIGURATION_ERROR"
    p.clients.assert_not_called()


@pytest.mark.parametrize("namespace", ["bad\nnamespace", "x" * 513])
def test_invalid_namespace_settings_fail_closed(production, namespace):
    with pytest.raises(RAGIntegrationError):
        load_configuration({**production.env, "PINECONE_NAMESPACE": namespace})


def test_wrong_corpus_or_forged_vector_id_query_hits_are_withheld(production):
    p = production
    records = pin_mock_corpus(p)
    good = next(iter(records.values()))
    for field, value in [("corpus_id", "0" * 64), ("record_id", "fake-record")]:
        hit = deepcopy(good)
        # Coherent flat/nested identity still must match pinned corpus/record ID.
        import json
        evidence = json.loads(hit["metadata"]["evidence_json"])
        evidence[field] = value
        hit["metadata"].update({field: value, "evidence_json": json.dumps(evidence)})
        if field == "record_id":
            hit["id"] = value
        p.dense.query.return_value = p.sparse.query.return_value = {"matches": [hit]}
        assert checked(ask(p.system.client()), 503)["code"] == "RAG_EVIDENCE_INVALID"


def test_cross_tenant_scope_rejected_before_corpus_cloud_fetch(production):
    p = production
    pin_mock_corpus(p)
    checked(ask(p.system.client("b")), 404)
    with pytest.raises(RAGIntegrationError):
        p.factory("tenant-b", "Tenant B", "lease-a")
    p.clients.assert_not_called()


def test_banner_stripping_rebuilds_canonical_spans_without_losing_unsigned_status(demo):
    d = demo
    from lease_rag.chunking import chunk_pdf, extract_document
    record = d["record"]
    chunks, _ = chunk_pdf(record["pdf_path"], record, ROOT / "data")
    pet = next(doc for doc in chunks if doc.metadata["section_id"] == "11")
    assert pet.metadata["page_numbers"] == [2]
    assert pet.metadata["document_status"] == "synthetic_unsigned"
    assert pet.metadata["document_sha256"] == d["binding"]["documents"][0]["document_sha256"]
    extracted = extract_document(record["pdf_path"], record, ROOT / "data")
    for chunk in chunks:
        for span in chunk.metadata["source_spans"]:
            assert not any(line in span["text"] for line in record["repeated_header_footer_lines"])
            page = extracted["pages"][span["page_number"] - 1]
            assert page["text"][span["char_start"]:span["char_end"]] == span["text"]
    assert "$250.00" in pet.metadata["source_text"]


def test_upstream_default_hybrid_weight():
    from lease_rag.retrieval import TenantHybridRetriever
    assert TenantHybridRetriever.model_fields["dense_weight"].default == 0.7


def test_synthetic_demo_through_corpus_format_preserves_all_approval_gates(demo):
    d, p = demo, demo["p"]
    from lease_rag.chunking import chunk_pdf
    from lease_rag.manifest import read_manifest
    from laga.synthetic_demo import DEMO_NOTICE
    p.config = d["config"]
    p.documents = [
        chunk for record in read_manifest(p.config.manifest_path, p.config.data_dir)
        for chunk in chunk_pdf(record["pdf_path"], record, p.config.data_dir)[0]
    ]
    p.snapshot = {
        **p.snapshot, "chunk_count": len(p.documents),
        "documents": {
            doc.metadata["document_id"]: {
                "access": doc.metadata["access"], "tenant_name": doc.metadata["tenant_name"],
            } for doc in p.documents
        },
    }
    p.snapshot_path, p.bindings_path = p.config.snapshot_path, p.config.bindings_path
    p.binding = d["binding"]
    records = pin_mock_corpus(p)
    config = replace(
        p.config,
        settings=type(p.config.settings)({
            **p.config.settings.values, "PINECONE_NAMESPACE": p.env["PINECONE_NAMESPACE"],
        }),
    )
    chosen = d["selected"].metadata["chunk_id"] + ":" + p.snapshot["corpus_id"][:24]
    p.dense.query.return_value = p.sparse.query.return_value = {"matches": [records[chosen]]}
    factory = ProductionRetrieverFactory(
        d["backend"], configuration_loader=lambda: config, clients_factory=p.clients,
    )
    d["backend"]._assistant.retriever_factory = factory
    response = d["backend"].post_assistant_messages(
        user={"id": "tenant-1"}, question="When does my lease expire?",
        scope={"type": "lease", "id": "lease-1"}, asOf="2026-11-05",
    )
    assert response["answer"].startswith(DEMO_NOTICE)
    assert response["status"] == "supported"
    for index in (p.dense, p.sparse):
        assert all("nc-chapter-42" not in key for call in index.fetch.call_args_list
                   for key in call.kwargs["ids"])
    blocked = ProductionRetrieverFactory(
        d["backend"], configuration_loader=lambda: replace(config, synthetic_demo_enabled=False),
        clients_factory=p.clients,
    )
    p.clients.reset_mock()
    with pytest.raises(RAGIntegrationError):
        blocked("tenant-1", "Maya Chen", "lease-1")
    p.clients.assert_not_called()

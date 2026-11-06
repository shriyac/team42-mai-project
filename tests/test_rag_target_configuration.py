"""Operator target pins only: no real keys, PDFs, snapshots or service calls."""
import json
from unittest.mock import Mock

import pytest

from laga.rag_configuration import RAGIntegrationError, load_configuration
from laga.rag_integration import ProductionRetrieverFactory
from test_production_rag import production, system

CORPUS = "74176289f06d1ecbcb70b901b1fb4fb1f6194194623a06502151ce431f005fc0"


def settings(**overrides):
    return {
        "LAGA_RAG_ENV_FILE": "",
        "LAGA_RAG_ENABLED": "true",
        "PINECONE_API_KEY": "fictional-pinecone-test-only",
        "NEBIUS_API_KEY": "fictional-embedding-test-only",
        "PINECONE_INDEX_NAME": "laga-rag",
        "PINECONE_SPARSE_INDEX_NAME": "laga-rag-sparse",
        "PINECONE_CLOUD": "aws",
        "PINECONE_REGION": "us-east-1",
        "PINECONE_NAMESPACE": "laga-hydrid",
        "LAGA_RAG_EXPECTED_CORPUS_ID": CORPUS,
        **overrides,
    }


def test_operator_target_preserves_exact_namespace_indexes_and_corpus():
    config = load_configuration(settings())
    assert config.settings.dense_index_name == "laga-rag"
    assert config.settings.sparse_index_name == "laga-rag-sparse"
    assert config.settings.namespace == "laga-hydrid"
    assert config.settings.get("PINECONE_CLOUD") == "aws"
    assert config.settings.get("PINECONE_REGION") == "us-east-1"
    assert config.expected_corpus_id == CORPUS
    assert config.synthetic_demo_enabled is False


@pytest.mark.parametrize("value", ["", "a" * 63, "A" * 64, "g" * 64, "a" * 65])
def test_malformed_expected_corpus_fails_safely(value):
    with pytest.raises(RAGIntegrationError) as error:
        load_configuration(settings(LAGA_RAG_EXPECTED_CORPUS_ID=value))
    assert error.value.code == "RAG_CONFIGURATION_ERROR"


def test_target_configuration_does_not_authorize_activation():
    with pytest.raises(RAGIntegrationError):
        load_configuration(settings(LAGA_RAG_ENABLED="false"))


def test_corpus_pin_is_optional_for_existing_integrations():
    env = settings()
    del env["LAGA_RAG_EXPECTED_CORPUS_ID"]
    assert load_configuration(env).expected_corpus_id is None


@pytest.mark.parametrize("snapshot_corpus", [None, "b" * 64])
def test_missing_or_different_pinned_corpus_stops_before_cloud(production, snapshot_corpus):
    # This is an existing fictional fixture, never an operational snapshot.
    env = {**production.env, "LAGA_RAG_EXPECTED_CORPUS_ID": CORPUS}
    snapshot_path = production.config.snapshot_path
    snapshot = json.loads(snapshot_path.read_text())
    if snapshot_corpus is None:
        snapshot.pop("corpus_id", None)
    else:
        snapshot["corpus_id"] = snapshot_corpus
    snapshot_path.write_text(json.dumps(snapshot))
    clients = Mock(side_effect=AssertionError("Cloud initialization must not occur"))
    factory = ProductionRetrieverFactory(
        production.system.service,
        configuration_loader=lambda: load_configuration(env),
        clients_factory=clients,
    )
    principal = production.system.profiles["a"]
    with pytest.raises(RAGIntegrationError) as error:
        factory.for_authorized_lease(
            principal=principal, organization_id="org-a",
            lease=production.system.service.get_workspace(user=principal)["leases"][0],
        )
    assert error.value.code == "RAG_CONFIGURATION_ERROR"
    clients.assert_not_called()

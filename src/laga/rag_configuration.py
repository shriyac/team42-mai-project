"""Opt-in retrieval configuration; environment overrides local dotenv values."""

from dataclasses import dataclass, field
import os
from pathlib import Path
import re

from .paths import resolve_project_path


class RAGIntegrationError(ValueError):
    """Only fixed, public messages cross the assistant boundary."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.public_message = message


CONFIG_ERROR = "RAG_CONFIGURATION_ERROR"
MAPPING_ERROR = "RAG_MAPPING_INVALID"
EVIDENCE_ERROR = "RAG_EVIDENCE_INVALID"
KEYS = (
    "LAGA_RAG_ENABLED", "LAGA_RAG_BINDINGS_FILE", "LAGA_RAG_MANIFEST_FILE",
    "LAGA_RAG_DATA_DIR", "LAGA_RAG_SNAPSHOT_FILE", "EMBEDDING_PROVIDER",
    "PINECONE_INDEX_NAME", "PINECONE_SPARSE_INDEX_NAME", "PINECONE_API_KEY",
    "NEBIUS_API_KEY", "FIREWORKS_API_KEY",
    "LAGA_RAG_SYNTHETIC_DEMO_ENABLED",
    "PINECONE_NAMESPACE", "PINECONE_CLOUD", "PINECONE_REGION",
    "LAGA_RAG_EXPECTED_CORPUS_ID",
)


def runtime_values(environ=None):
    """Read only retrieval settings, never the whole process secret environment."""
    environ = os.environ if environ is None else environ
    explicit = environ.get("LAGA_RAG_ENV_FILE")
    path = resolve_project_path(explicit or ".env")
    if explicit and not path.is_file():
        raise RAGIntegrationError(CONFIG_ERROR, "The configured local RAG settings file is unavailable.")
    local = {}
    if path.is_file():
        from dotenv import dotenv_values
        local = dotenv_values(path, interpolate=False)
    return {
        key: environ[key] if key in environ else local[key]
        for key in KEYS if key in environ or key in local
    }


def activation_requested():
    """Invalid nonempty flags become explicit request-time configuration errors."""
    explicit = os.environ.get("LAGA_RAG_ENABLED")
    if explicit is not None and explicit.strip().lower() in {"", "false", "0"}:
        return False
    try:
        return str(runtime_values().get("LAGA_RAG_ENABLED") or "false").strip().lower() not in {
            "", "false", "0",
        }
    except Exception:
        # Keep the API available; the retrieval boundary returns a safe error.
        return True


@dataclass(frozen=True)
class RuntimeRAGConfiguration:
    settings: object = field(repr=False)
    snapshot_path: Path
    manifest_path: Path
    bindings_path: Path
    data_dir: Path
    synthetic_demo_enabled: bool = False
    expected_corpus_id: str | None = None


def load_configuration(environ=None):
    try:
        from lease_rag.config import ROOT, PROVIDERS, Settings
        values = runtime_values(environ)
        if str(values.get("LAGA_RAG_ENABLED") or "").strip().lower() not in {"true", "1"}:
            raise ValueError("Retrieval is not explicitly enabled.")
        demo = str(values.get("LAGA_RAG_SYNTHETIC_DEMO_ENABLED") or "false").strip().lower()
        if demo not in {"true", "1", "false", "0"}:
            raise ValueError("Invalid synthetic demo setting.")
        expected_corpus = values.get("LAGA_RAG_EXPECTED_CORPUS_ID")
        if expected_corpus is not None and (
            not isinstance(expected_corpus, str)
            or not re.fullmatch(r"[0-9a-f]{64}", expected_corpus)
        ):
            raise ValueError("Invalid expected corpus identity.")
        settings = Settings({
            key: value for key, value in values.items() if not key.startswith("LAGA_")
        }, root=ROOT)
        for name in (settings.dense_index_name, settings.sparse_index_name):
            if not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,43}[a-z0-9])?", name):
                raise ValueError("Invalid Pinecone index name.")
        if settings.dense_index_name == settings.sparse_index_name:
            raise ValueError("Dense and sparse index names must differ.")
        if settings.namespace and (
            len(settings.namespace.encode("utf-8")) > 512
            or any(ord(char) < 32 or ord(char) == 127 for char in settings.namespace)
        ):
            raise ValueError("Invalid Pinecone namespace.")
        settings.require("PINECONE_API_KEY")
        settings.require(PROVIDERS[settings.profile["provider"]][0])
        return RuntimeRAGConfiguration(
            settings=settings,
            snapshot_path=resolve_project_path(
                values.get("LAGA_RAG_SNAPSHOT_FILE") or "artifacts/lease_rag_local/active.json"),
            manifest_path=resolve_project_path(values.get("LAGA_RAG_MANIFEST_FILE") or "documents.json"),
            bindings_path=resolve_project_path(values.get("LAGA_RAG_BINDINGS_FILE") or "rag_bindings.json"),
            data_dir=resolve_project_path(values.get("LAGA_RAG_DATA_DIR") or "data"),
            synthetic_demo_enabled=demo in {"true", "1"},
            expected_corpus_id=expected_corpus,
        )
    except RAGIntegrationError:
        raise
    except Exception:
        raise RAGIntegrationError(
            CONFIG_ERROR, "RAG settings are incomplete or invalid; retrieval has not been enabled.",
        ) from None

"""Read-only production bridge to Monica's unchanged TenantHybridRetriever."""

from copy import deepcopy
from collections.abc import Mapping

from .rag_configuration import (
    CONFIG_ERROR, EVIDENCE_ERROR, RAGIntegrationError, activation_requested, load_configuration,
)
from .rag_mapping import verify_scope


def production_factory_from_environment(backend):
    return ProductionRetrieverFactory(backend) if activation_requested() else None


def _field(value, name):
    return value[name] if isinstance(value, Mapping) else getattr(value, name)


def _indexes(pc, config, snapshot):
    """Describe existing resources only. Never call ingestion/prepare/create."""
    indexes = []
    try:
        for sparse, name in [
            (False, config.settings.dense_index_name), (True, config.settings.sparse_index_name),
        ]:
            description = pc.describe_index(name)
            if (
                _field(description, "name") != name
                or _field(description, "metric") != ("dotproduct" if sparse else "cosine")
                or _field(description, "vector_type") != ("sparse" if sparse else "dense")
                or (not sparse and _field(description, "dimension") != config.settings.profile["dimensions"])
                or _field(_field(description, "status"), "ready") is not True
                or not isinstance(_field(description, "host"), str) or not _field(description, "host")
            ):
                raise RAGIntegrationError(
                    CONFIG_ERROR, "Existing Pinecone indexes are not ready or do not match the ingestion profile.",
                )
            index = pc.Index(host=_field(description, "host"))
            namespaces = _field(index.describe_index_stats(), "namespaces")
            count = _field(namespaces[snapshot["namespace"]], "vector_count")
            if type(count) is not int or count != snapshot["chunk_count"]:
                raise RAGIntegrationError(
                    CONFIG_ERROR, "The pinned Pinecone namespace is incomplete or inconsistent.",
                )
            indexes.append(index)
        return indexes
    except RAGIntegrationError:
        raise
    except (KeyError, AttributeError, TypeError):
        raise RAGIntegrationError(
            CONFIG_ERROR, "The configured Pinecone indexes or namespace could not be verified.",
        ) from None
    except Exception:
        raise RAGIntegrationError(
            "RAG_UNAVAILABLE", "Pinecone retrieval resources are unavailable.",
        ) from None


def normalize_document(document, scope):
    """Retain original source identity; enrich only verified backend identities."""
    from langchain_core.documents import Document
    from lease_rag.manifest import tenant_key

    try:
        meta = deepcopy(document.metadata)
        row = scope.bindings[meta["document_id"]]
        canonical = scope.chunks[meta["chunk_id"]]
        if document.page_content != canonical.page_content:
            raise ValueError("Stored chunk text differs from the verified PDF extraction.")
        for key, expected in canonical.metadata.items():
            if key == "lease_id" and meta.get(key) is None:
                continue  # The explicit verified manifest supplies this identity.
            if key not in meta or meta[key] != expected:
                raise ValueError("Stored source provenance differs from the verified PDF extraction.")
        if (
            meta.get("access") != "tenant" or meta.get("document_type") != "lease"
            or meta.get("document_status") != "signed"
            or meta.get("tenant_name") != tenant_key(scope.tenant_name)
            or meta.get("document_sha256") != row["document_sha256"]
            or not isinstance(meta.get("chunk_id"), str) or not meta["chunk_id"].strip()
        ):
            raise ValueError("Invalid lease evidence identity or unsigned/template content.")
        for key, expected in {
            "tenant_id": scope.tenant_id, "organization_id": scope.organization_id,
            "lease_id": scope.lease_id, "backend_document_id": row["backend_document_id"],
        }.items():
            if meta.get(key) is not None and meta[key] != expected:
                raise ValueError("Retrieved evidence conflicts with verified ownership.")
            meta[key] = expected
        pages, spans, body = meta.get("page_numbers"), meta.get("source_spans"), meta.get("source_text")
        if (
            not isinstance(pages, list) or not pages
            or any(type(page) is not int or page < 1 for page in pages)
            or len(set(pages)) != len(pages)
            or not isinstance(spans, list) or not spans
            or not isinstance(body, str) or not body.strip()
            or not isinstance(meta.get("section_id"), str) or not meta["section_id"].strip()
            or (meta.get("clause_id") is not None and not isinstance(meta["clause_id"], str))
            or not isinstance(meta.get("citation_label"), str) or not meta["citation_label"].strip()
        ):
            raise ValueError("Missing source provenance.")
        cursor = 0
        for span in spans:
            if (
                not isinstance(span, dict) or span.get("page_number") not in pages
                or type(span.get("page_number")) is not int
                or type(span.get("char_start")) is not int or span["char_start"] < 0
                or type(span.get("char_end")) is not int or span["char_end"] <= span["char_start"]
                or not isinstance(span.get("text"), str) or not span["text"].strip()
                or len(span["text"]) != span["char_end"] - span["char_start"]
            ):
                raise ValueError("Invalid source span.")
            offset = body.find(span["text"], cursor)
            if offset < 0 or body[cursor:offset].strip():
                raise ValueError("Source text differs from citation spans.")
            cursor = offset + len(span["text"])
        if body[cursor:].strip() or set(pages) != {span["page_number"] for span in spans}:
            raise ValueError("Source text/page coverage is incomplete.")
        if meta.get("page_number") is not None and (
            type(meta["page_number"]) is not int or meta["page_number"] not in pages
        ):
            raise ValueError("Conflicting scalar citation page.")
        # Retrieval text can contain breadcrumbs/parent clauses: only the actual
        # source body is handed to the lease agent as answer evidence.
        return Document(page_content=body, metadata=meta)
    except Exception:
        raise RAGIntegrationError(
            EVIDENCE_ERROR, "Retrieved evidence does not match the verified lease source metadata.",
        ) from None


class BoundRetrieverFactory:
    """Per-request scope and failure state; never shared between authenticated calls."""

    def __init__(self, scope, delegate):
        self.scope, self.delegate, self.failure = scope, delegate, None
        self.document_ids = frozenset(scope.bindings)

    def __call__(self, tenant_id, tenant_name, lease_id):
        if (tenant_id, tenant_name, lease_id) != (
            self.scope.tenant_id, self.scope.tenant_name, self.scope.lease_id,
        ):
            self.failure = RAGIntegrationError(
                "RAG_MAPPING_INVALID", "The retrieval call does not match the verified tenant lease.",
            )
            raise self.failure
        return self

    def invoke(self, query):
        try:
            return [normalize_document(doc, self.scope) for doc in self.delegate.invoke(query)]
        except RAGIntegrationError as error:
            self.failure = error
            raise
        except PermissionError:
            self.failure = RAGIntegrationError(
                EVIDENCE_ERROR, "Pinecone returned evidence outside the verified tenant scope.",
            )
            raise self.failure from None
        except Exception:
            self.failure = RAGIntegrationError(
                "RAG_UNAVAILABLE", "The production lease retriever could not complete this request.",
            )
            raise self.failure from None

    def check_failure(self):
        if self.failure is not None:
            raise self.failure


class ProductionRetrieverFactory:
    """factory(tenant_id, tenant_name, lease_id) -> retriever.invoke(query).

    clients_factory is an internal test seam, not environment/browser config.
    Every request revalidates local bindings and SQLite before any client use.
    """

    def __init__(self, backend, *, configuration_loader=load_configuration, clients_factory=None):
        self.backend = backend
        self.configuration_loader = configuration_loader
        self.clients_factory = clients_factory

    def for_authorized_lease(self, *, principal, organization_id, lease):
        config = self.configuration_loader()
        scope = verify_scope(
            self.backend, config, principal["id"], principal["name"], lease["id"],
        )
        if (
            scope.organization_id != organization_id
            or scope.backend_document_ids != frozenset(lease.get("documents", []))
            or lease["tenantId"] != scope.tenant_id
        ):
            raise RAGIntegrationError(
                "RAG_MAPPING_INVALID", "The authorized lease changed before retrieval could start.",
            )
        try:
            pc, embeddings = (
                self.clients_factory(config.settings) if self.clients_factory
                else config.settings.clients()
            )
        except Exception:
            raise RAGIntegrationError(
                "RAG_UNAVAILABLE", "Production retrieval clients could not be initialized.",
            ) from None
        dense, sparse = _indexes(pc, config, scope.snapshot)
        from lease_rag.retrieval import TenantHybridRetriever
        delegate = TenantHybridRetriever(
            dense_index=dense, sparse_index=sparse, embeddings=embeddings, pc=pc,
            snapshot=deepcopy(scope.snapshot), tenant_name=scope.tenant_name,
            document_ids=sorted(scope.bindings),
        )
        return BoundRetrieverFactory(scope, delegate)

    def __call__(self, tenant_id, tenant_name, lease_id):
        from contextlib import closing
        try:
            with closing(self.backend._connect()) as db:
                principal, org = self.backend._principal(
                    db, {"id": tenant_id}, role="tenant", permission="lease:read",
                )
                lease, _ = self.backend._lease(db, org, principal, lease_id)
        except Exception:
            raise RAGIntegrationError(
                "RAG_MAPPING_INVALID", "The tenant and lease could not be authorized for retrieval.",
            ) from None
        if principal["name"] != tenant_name:
            raise RAGIntegrationError("RAG_MAPPING_INVALID", "The tenant name does not match the backend account.")
        return self.for_authorized_lease(principal=principal, organization_id=org, lease=lease)(
            tenant_id, tenant_name, lease_id,
        )

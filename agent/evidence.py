"""Document adapters and fail-closed tenant/lease scope checks."""

from collections.abc import Mapping, Sequence
from typing import Any, Protocol
import unicodedata


class Retriever(Protocol):
    def invoke(self, query: str) -> Sequence[Any]: ...


class RetrieverFactory(Protocol):
    """Adapt trusted IDs to a scoped retriever, including authorized document IDs."""

    def __call__(self, tenant_id: str, tenant_name: str, lease_id: str) -> Retriever: ...


def tenant_key(value: Any) -> str:
    return (
        " ".join(unicodedata.normalize("NFKC", value).casefold().split())
        if isinstance(value, str) else ""
    )


def is_authorized_lease_document(
    document: Any, *, tenant_id: str, tenant_name: str, lease_id: str
) -> bool:
    metadata = getattr(document, "metadata", None)
    if not isinstance(metadata, Mapping) or metadata.get("lease_id") != lease_id:
        return False
    if not isinstance(metadata.get("document_id"), str) or not metadata["document_id"].strip():
        return False
    if metadata.get("access") == "shared" or metadata.get("document_type") == "statute":
        return False
    has_owner = False
    if "tenant_id" in metadata:
        has_owner = True
        if metadata["tenant_id"] != tenant_id:
            return False
    if "tenant_name" in metadata:
        has_owner = True
        if tenant_key(metadata["tenant_name"]) != tenant_key(tenant_name):
            return False
    return has_owner


def source_text(document: Any) -> str:
    """Prefer source spans over enriched retrieval text; never invent a quote."""
    metadata = getattr(document, "metadata", {})
    spans = metadata.get("source_spans", []) if isinstance(metadata, Mapping) else []
    if isinstance(spans, Sequence) and not isinstance(spans, (str, bytes)):
        texts = [
            span["text"].strip() for span in spans
            if isinstance(span, Mapping) and isinstance(span.get("text"), str)
            and span["text"].strip()
        ]
        if texts:
            return "\n".join(texts)
    quote = metadata.get("quote") if isinstance(metadata, Mapping) else None
    if isinstance(quote, str) and quote.strip():
        return quote.strip()
    content = getattr(document, "page_content", "")
    return content.strip() if isinstance(content, str) else ""


def citation_from_document(document: Any, source_id: str) -> dict[str, Any] | None:
    metadata = getattr(document, "metadata", {})
    if not isinstance(metadata, Mapping) or not source_text(document):
        return None
    if not metadata.get("document_id") or not metadata.get("lease_id"):
        return None
    page = metadata.get("page_number", metadata.get("page"))
    if not isinstance(page, int) or isinstance(page, bool) or page < 1:
        pages = metadata.get("page_numbers", [])
        if not isinstance(pages, (list, tuple)):
            pages = []
        spans = metadata.get("source_spans", [])
        if isinstance(spans, (list, tuple)):
            pages = [*pages, *(s.get("page_number") for s in spans if isinstance(s, Mapping))]
        page = next(
            (p for p in pages if isinstance(p, int) and not isinstance(p, bool) and p > 0),
            None,
        )
    clause = metadata.get("clause_id", metadata.get("section_id", ""))
    return {
        "source_id": source_id,
        "document_id": metadata["document_id"],
        "lease_id": metadata["lease_id"],
        "page_number": page,
        "clause_id": clause if isinstance(clause, str) else "",
        "source_text": source_text(document),
        "document_title": str(metadata.get("document_title", "")),
        "document_type": str(metadata.get("document_type", "")),
    }


def merge_documents(existing: Sequence[Any], incoming: Sequence[Any]) -> list[Any]:
    result = []
    seen = set()
    for document in [*existing, *incoming]:
        metadata = getattr(document, "metadata", {})
        identity = (
            metadata.get("document_id"), metadata.get("chunk_id"),
            metadata.get("clause_id"), source_text(document),
        )
        if identity not in seen:
            seen.add(identity)
            result.append(document)
    return result


class MockLeaseRetriever:
    """Synthetic evidence is supplied by callers/tests; no built-in lease data."""

    def __init__(self, documents=(), *, tenant_id, tenant_name, lease_id,
                 results_by_query=None, query_observer=None):
        self.documents = list(documents)
        self.scope = dict(tenant_id=tenant_id, tenant_name=tenant_name, lease_id=lease_id)
        self.results_by_query = dict(results_by_query or {})
        self.query_observer = query_observer

    def invoke(self, query: str) -> list[Any]:
        if self.query_observer:
            self.query_observer(query)
        return [
            doc for doc in self.results_by_query.get(query, self.documents)
            if is_authorized_lease_document(doc, **self.scope)
        ]


class MockLeaseRetrieverFactory:
    def __init__(self, documents=(), *, results_by_query=None):
        self.documents = list(documents)
        self.results_by_query = dict(results_by_query or {})
        self.calls = []
        self.queries = []

    def __call__(self, tenant_id, tenant_name, lease_id):
        self.calls.append((tenant_id, tenant_name, lease_id))
        return MockLeaseRetriever(
            self.documents, tenant_id=tenant_id, tenant_name=tenant_name,
            lease_id=lease_id, results_by_query=self.results_by_query,
            query_observer=self.queries.append,
        )

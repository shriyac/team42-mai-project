"""Authorized, session-bound assistant integration without authentication/DB rewrites.

Retrieval is deliberately unconfigured by default. Test evidence is only used
when an internal caller explicitly injects a retriever factory.
"""

from collections.abc import Sequence
from contextvars import ContextVar
from copy import deepcopy
from hashlib import sha256
from threading import RLock
import uuid

from .backend_api import APIError
from .assistant_adapter import adapt_answer
from .rag_configuration import RAGIntegrationError
from .rag_integration import ProductionRetrieverFactory


_SESSION_BINDING = ContextVar("laga_assistant_session_binding", default=None)


def call_in_assistant_session(method, *, session_token, **kwargs):
    """Bind a pre-authenticated HTTP session for this synchronous service call.

    This helper does not authenticate or accept browser-selected identity.
    The existing HTTP handler verifies the session and CSRF before calling it.
    Context is always reset, including on failure or worker-thread reuse.
    """
    if not isinstance(session_token, str) or not session_token:
        raise APIError(401, "UNAUTHENTICATED", "Please sign in to continue.")
    marker = _SESSION_BINDING.set(sha256(session_token.encode()).hexdigest())
    try:
        return method(**kwargs)
    finally:
        _SESSION_BINDING.reset(marker)


def run_laga_agent(*args, **kwargs):
    """Lazy import keeps an unconfigured backend independent of agent packaging."""
    from agent.graph import run_laga_agent as run
    return run(*args, **kwargs)


class ThreadRegistry:
    """Bounded, process-local ownership only; no conversation transcript is stored."""

    def __init__(self, *, now, lifetime, capacity=10000):
        self.now, self.lifetime, self.capacity = now, lifetime, capacity
        self._threads = {}
        self._lock = RLock()

    def _prune(self):
        current = self.now()
        self._threads = {
            key: item for key, item in self._threads.items() if item[1] > current
        }

    def check(self, thread_id, owner):
        with self._lock:
            self._prune()
            record = self._threads.get(thread_id)
            if record is None or record[0] != owner:
                raise APIError(404, "NOT_FOUND", "Conversation not found.")

    def remember(self, thread_id, owner, *, existing):
        with self._lock:
            self._prune()
            if existing:
                self.check(thread_id, owner)
                return
            if len(self._threads) >= self.capacity:
                raise APIError(429, "ASSISTANT_BUSY", "Conversation capacity reached. Try again later.")
            self._threads[thread_id] = (owner, self.now() + self.lifetime)


class AssistantIntegration:
    def __init__(self, *, retriever_factory, now, session_seconds):
        self.retriever_factory = retriever_factory
        self.threads = ThreadRegistry(now=now, lifetime=session_seconds)

    def answer(
        self, *, principal, organization_id, lease, question, as_of, thread_id,
        validate_response,
    ):
        # Direct service calls are an internal trusted boundary. They cannot
        # reuse HTTP session-bound threads, nor can a new login reuse an old one.
        owner = (
            organization_id, principal["id"], lease["id"],
            _SESSION_BINDING.get() or "internal-service-call",
        )
        existing = thread_id is not None
        if existing:
            self.threads.check(thread_id, owner)
        if self.retriever_factory is None:
            raise APIError(
                503, "RAG_UNAVAILABLE",
                "Lease retrieval is not configured. Please try again when the service is available.",
            )

        allowed_documents = lease.get("documents", [])
        if (
            not isinstance(allowed_documents, list) or not allowed_documents
            or any(not isinstance(value, str) or not value for value in allowed_documents)
        ):
            raise APIError(503, "RAG_UNAVAILABLE", "No authorized lease documents are available.")

        configured_factory = self.retriever_factory
        if isinstance(configured_factory, ProductionRetrieverFactory):
            try:
                configured_factory = configured_factory.for_authorized_lease(
                    principal=principal, organization_id=organization_id, lease=lease,
                )
                # Only a verified, server-owned production scope may translate
                # backend document IDs to different immutable Pinecone IDs.
                allowed_documents = list(configured_factory.document_ids)
            except RAGIntegrationError as error:
                raise APIError(503, error.code, error.public_message) from None
            except Exception:
                raise APIError(503, "RAG_UNAVAILABLE", "Production lease retrieval is unavailable.") from None
        evidence = []
        trusted = (principal["id"], principal["name"], lease["id"])
        allowed_ids = frozenset(allowed_documents)

        def scoped_factory(tenant_id, tenant_name, lease_id):
            if (tenant_id, tenant_name, lease_id) != trusted:
                raise ValueError("Unexpected retrieval scope.")
            delegate = configured_factory(tenant_id, tenant_name, lease_id)

            class ScopedRetriever:
                def invoke(self, query):
                    from agent.evidence import (
                        citation_from_document, is_authorized_lease_document,
                    )
                    documents = delegate.invoke(query)
                    if not isinstance(documents, Sequence) or isinstance(documents, (str, bytes)):
                        raise ValueError("Invalid retrieval response.")
                    accepted = []
                    for document in documents:
                        metadata = getattr(document, "metadata", {})
                        if (
                            not isinstance(metadata, dict)
                            or metadata.get("document_id") not in allowed_ids
                            or metadata.get("organization_id", organization_id) != organization_id
                            or not is_authorized_lease_document(
                                document, tenant_id=tenant_id,
                                tenant_name=tenant_name, lease_id=lease_id,
                            )
                        ):
                            continue
                        record = citation_from_document(document, "S0")
                        if record is None:
                            continue
                        identity = {k: v for k, v in record.items() if k != "source_id"}
                        section_title = metadata.get("section_title")
                        clause = record["clause_id"] or metadata.get("section_id") or ""
                        section = clause
                        if isinstance(section_title, str) and section_title.strip():
                            section = (
                                f"{clause} — {section_title}" if clause and clause != section_title
                                else section_title
                            )
                        evidence.append(deepcopy({"identity": identity, "section": section}))
                        accepted.append(document)
                    return accepted

            return ScopedRetriever()

        response_thread = thread_id if existing else str(uuid.uuid4())
        try:
            result = run_laga_agent(
                question=question, tenant_id=trusted[0], tenant_name=trusted[1],
                lease_id=trusted[2], as_of=as_of, retriever_factory=scoped_factory,
            )
        except Exception:
            raise APIError(
                503, "ASSISTANT_UNAVAILABLE",
                "The lease assistant could not complete this request. Please try again.",
            ) from None
        if isinstance(self.retriever_factory, ProductionRetrieverFactory):
            try:
                configured_factory.check_failure()
            except RAGIntegrationError as error:
                raise APIError(503, error.code, error.public_message) from None
        try:
            response = adapt_answer(result, thread_id=response_thread, evidence=evidence)
            if (
                isinstance(self.retriever_factory, ProductionRetrieverFactory)
                and configured_factory.is_synthetic_demo
            ):
                from .synthetic_demo import DEMO_NOTICE
                response["answer"] = DEMO_NOTICE + response["answer"]
            validate_response(response)
        except Exception:
            raise APIError(
                503, "BACKEND_CONTRACT_ERROR",
                "The lease assistant returned an incompatible response.",
            ) from None
        self.threads.remember(response_thread, owner, existing=existing)
        return response

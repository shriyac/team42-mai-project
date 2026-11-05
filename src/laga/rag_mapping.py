"""Verify operator bindings against SQLite and pinned ingestion inputs, read-only."""

from contextlib import closing
from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
import json
import re

from .rag_configuration import CONFIG_ERROR, MAPPING_ERROR, RAGIntegrationError
from .synthetic_demo import eligible_status


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


@dataclass(frozen=True)
class VerifiedScope:
    tenant_id: str
    tenant_name: str
    lease_id: str
    organization_id: str
    backend_document_ids: frozenset
    bindings: dict
    snapshot: dict
    chunks: dict
    property_id: str = ""
    synthetic_document_ids: frozenset = frozenset()


def verify_scope(backend, config, tenant_id, tenant_name, lease_id):
    """Neither filenames, PDF content, nor a client-provided identity grant access."""
    from lease_rag.manifest import read_manifest, tenant_key
    from lease_rag.retrieval import authorized_scope, load_snapshot

    try:
        with closing(backend._connect()) as db:
            principal, organization_id = backend._principal(
                db, {"id": tenant_id}, role="tenant", permission="lease:read",
            )
            lease, _ = backend._lease(db, organization_id, principal, lease_id)
        if tenant_key(tenant_name) != tenant_key(principal["name"]):
            raise ValueError("Caller name differs from the authoritative account.")
        documents = lease.get("documents")
        if (
            not isinstance(documents, list) or not documents
            or any(not isinstance(item, str) or not item.strip() for item in documents)
            or len(set(documents)) != len(documents)
            or lease["tenantId"] != tenant_id
            or tenant_key(lease["tenantName"]) != tenant_key(principal["name"])
        ):
            raise ValueError("Invalid authoritative lease document registry.")
    except Exception:
        raise RAGIntegrationError(
            MAPPING_ERROR, "The tenant and lease could not be matched to authoritative backend records.",
        ) from None

    try:
        snapshot_hash = digest(config.snapshot_path)
        snapshot = load_snapshot(config.settings, config.snapshot_path)
        if (
            type(snapshot["schema_version"]) is not int or snapshot["schema_version"] != 1
            or snapshot_hash != digest(config.snapshot_path)
            or not re.fullmatch(r"leases-v1-[0-9a-f]{24}", snapshot["namespace"])
            or type(snapshot["chunk_count"]) is not int or snapshot["chunk_count"] < 1
            or not isinstance(snapshot["documents"], dict) or not snapshot["documents"]
        ):
            raise ValueError("Invalid ingestion snapshot.")
    except FileNotFoundError:
        raise RAGIntegrationError(
            "RAG_UNAVAILABLE", "The verified ingestion snapshot is unavailable.",
        ) from None
    except Exception:
        raise RAGIntegrationError(
            CONFIG_ERROR, "The ingestion snapshot does not match the configured indexes or embedding profile.",
        ) from None

    try:
        manifest_hash = digest(config.manifest_path)
        bindings = json.loads(config.bindings_path.read_text(encoding="utf-8"))
        if (
            set(bindings) != {"schema_version", "snapshot_sha256", "manifest_sha256", "documents"}
            or type(bindings["schema_version"]) is not int or bindings["schema_version"] != 1
            or bindings["snapshot_sha256"] != snapshot_hash
            or bindings["manifest_sha256"] != manifest_hash
            or not isinstance(bindings["documents"], list) or not bindings["documents"]
        ):
            raise ValueError("Unverified ingestion inputs.")
        manifest = {
            item["document_id"]: item
            for item in read_manifest(config.manifest_path, config.data_dir)
        }
        if manifest_hash != digest(config.manifest_path):
            raise ValueError("Manifest changed during verification.")
        fields = {
            "organization_id", "tenant_id", "tenant_name", "lease_id",
            "backend_document_id", "pinecone_document_id", "document_sha256",
        }
        seen_backend, seen_pinecone, selected, chunks = set(), set(), {}, {}
        synthetic_ids = set()
        for row in bindings["documents"]:
            if (
                not isinstance(row, dict) or set(row) != fields
                or any(not isinstance(value, str) or not value.strip() for value in row.values())
                or not re.fullmatch(r"[0-9a-f]{64}", row["document_sha256"])
            ):
                raise ValueError("Invalid binding record.")
            backend_key = (row["organization_id"], row["lease_id"], row["backend_document_id"])
            if backend_key in seen_backend or row["pinecone_document_id"] in seen_pinecone:
                raise ValueError("Ambiguous or duplicated document ownership.")
            seen_backend.add(backend_key)
            seen_pinecone.add(row["pinecone_document_id"])
            if row["tenant_id"] != tenant_id or row["lease_id"] != lease_id:
                continue
            if (
                row["organization_id"] != organization_id
                or tenant_key(row["tenant_name"]) != tenant_key(principal["name"])
                or row["backend_document_id"] not in documents
            ):
                raise ValueError("Binding conflicts with SQLite ownership.")
            record = manifest[row["pinecone_document_id"]]
            if (
                record["access"] != "tenant" or record["document_type"] != "lease"
                or not eligible_status(
                    record["document_status"], enabled=config.synthetic_demo_enabled,
                    organization_id=organization_id, tenant_id=tenant_id,
                    tenant_name=principal["name"], lease_id=lease_id,
                    property_id=lease["propertyId"],
                    backend_document_id=row["backend_document_id"],
                    pinecone_document_id=row["pinecone_document_id"],
                    document_sha256=row["document_sha256"],
                )
                or (record["document_status"] == "synthetic_unsigned"
                    and record.get("property_id") != lease["propertyId"])
                or record["tenant_name"] != tenant_key(principal["name"])
                or any(record.get(key) != row[key] for key in (
                    "organization_id", "tenant_id", "lease_id", "backend_document_id",
                ))
                or digest(record["pdf_path"]) != row["document_sha256"]
                or snapshot["documents"][row["pinecone_document_id"]] != {
                    "access": "tenant", "tenant_name": tenant_key(principal["name"]),
                }
            ):
                raise ValueError("Manifest, PDF, snapshot and backend ownership disagree.")
            # Reuse the original read-only chunker to establish a local canonical
            # evidence ledger. Matching identity labels alone would not detect
            # a stored chunk whose body/spans were corrupted or mislabelled.
            from lease_rag.chunking import chunk_pdf
            canonical, report = chunk_pdf(record["pdf_path"], record, config.data_dir)
            if report["document_sha256"] != row["document_sha256"]:
                raise ValueError("PDF changed during verification.")
            for chunk in canonical:
                if chunk.metadata["chunk_id"] in chunks:
                    raise ValueError("Duplicate canonical chunk.")
                chunks[chunk.metadata["chunk_id"]] = chunk
            selected[row["pinecone_document_id"]] = deepcopy(row)
            if record["document_status"] == "synthetic_unsigned":
                synthetic_ids.add(row["pinecone_document_id"])
        if (
            {row["backend_document_id"] for row in selected.values()} != set(documents)
            or not chunks or len(chunks) > snapshot["chunk_count"]
        ):
            raise ValueError("Every backend lease document requires a verified mapping.")
        authorized_scope(snapshot, principal["name"], list(selected))
        # Preserve Monica's algorithm; narrow its registry so shared references
        # and other leases cannot enter either dense or sparse query filters.
        scoped = deepcopy(snapshot)
        scoped["documents"] = {
            key: deepcopy(snapshot["documents"][key]) for key in selected
        }
        return VerifiedScope(
            tenant_id=tenant_id, tenant_name=principal["name"], lease_id=lease_id,
            organization_id=organization_id, backend_document_ids=frozenset(documents),
            bindings=selected, snapshot=scoped,
            chunks=chunks,
            property_id=lease["propertyId"], synthetic_document_ids=frozenset(synthetic_ids),
        )
    except Exception:
        raise RAGIntegrationError(
            MAPPING_ERROR,
            "Verified ingestion bindings are missing or inconsistent with this tenant's lease documents.",
        ) from None

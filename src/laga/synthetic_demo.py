"""Narrow source-eligibility policy, not ingestion or binding approval."""

MAYA_PDF_SHA256 = "4a8c24f993152af5f4a61da328b3fcdf0932e2438114b20b343c5ef1d11dbf55"
DEMO_NOTICE = (
    "Synthetic unsigned demo fixture — not a signed or legally validated lease.\n\n"
)


def eligible_status(status, *, enabled, organization_id, tenant_id, tenant_name,
                    lease_id, property_id, backend_document_id,
                    pinecone_document_id, document_sha256):
    """Production stays signed-only; opt-in adds exactly one reviewed fixture.

    This approval covers the source fixture only. It never substitutes for
    verified ownership, manifest/snapshot pins, index checks or canonical text.
    """
    if status == "signed":
        return True
    return (
        enabled is True and status == "synthetic_unsigned"
        and (
            organization_id, tenant_id, tenant_name, lease_id, property_id,
            backend_document_id, pinecone_document_id, document_sha256,
        ) == (
            "org-alder-demo", "tenant-1", "Maya Chen", "lease-1", "property-1",
            "lease-document-1", "lease-document-1", MAYA_PDF_SHA256,
        )
    )

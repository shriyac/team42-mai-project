"""Atomic, repeat-safe local initialization from the bundled fictional dataset.

No Node/browser/external API is required at runtime. Existing populated databases
are left alone. A random per-installation login password is saved privately;
passwords, sessions and user edits are never reset by subsequent starts.
"""
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import secrets
import textwrap
import tempfile

from .backend_api import BackendAPI
from .paths import PROJECT_ROOT, resolve_project_path, reference, is_absolute_reference, legacy_basename, display_reference

ROOT = PROJECT_ROOT


def policy_pdf(policy):
    """Build a small valid native-text PDF of the fictional policy scenario."""
    lines = ["LAGA - SYNTHETIC POLICY / TEST DATA ONLY", policy["title"],
             f"Document: {policy['id']} / version {policy['version']}",
             f"State: {policy['state']} / property: {policy['propertyId'] or 'organization-wide'}",
             f"Effective: {policy['effectiveFrom']} / until: {policy['effectiveTo'] or 'open-ended'}", ""]
    for paragraph in [policy["description"], policy["excerpt"],
                      "This fictional policy is for local development only. It is not legal advice or an approved lease form.",
                      "Processing and legal review are pending. No compliance certification is supplied."]:
        lines.extend(textwrap.wrap(paragraph, 85))
        lines.append("")
    def escape(value):
        return value.encode("ascii", "replace").decode().replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    commands = ["BT /F1 11 Tf 48 744 Td 15 TL"]
    commands.extend(("T* " if i else "")+f"({escape(line)}) Tj" for i, line in enumerate(lines))
    commands.append("ET")
    stream = "\n".join(commands).encode("ascii")
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
               b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
               b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
               f"<< /Length {len(stream)} >>\nstream\n".encode()+stream+b"\nendstream"]
    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, 1):
        offsets.append(len(pdf))
        pdf.extend(f"{index} 0 obj\n".encode()+obj+b"\nendobj\n")
    xref = len(pdf)
    pdf.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010} 00000 n \n".encode())
    pdf.extend(f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return bytes(pdf)


def _credential_document(document, database, credentials, *, relocating=False):
    """Migrate only location metadata; retain passwords and account records unchanged."""
    if document.get("pathBase") == "Laga":
        expected = resolve_project_path(document["database"])
    elif document.get("pathBase") == "credentialsDirectory":
        expected = (credentials.parent / document["database"]).resolve()
    elif is_absolute_reference(document.get("database", "")):
        # Legacy snapshots can originate on either OS or in a relocated checkout.
        expected = database if legacy_basename(document["database"]) == database.name else None
    else:
        expected = None
    if (expected != database and not relocating) or document.get("synthetic") is not True:
        raise ValueError("Existing bootstrap credential file does not match this database")
    if database.is_relative_to(PROJECT_ROOT):
        document.update(database=database.relative_to(PROJECT_ROOT).as_posix(), pathBase="Laga")
    else:
        document.update(database=reference(database, credentials.parent), pathBase="credentialsDirectory")
    return document


def _write_credentials(path, text):
    """Atomically update only location metadata using a private adjacent temp file."""
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, prefix=".bootstrap-", delete=False) as output:
            temporary = Path(output.name)
            output.write(text)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def bootstrap_database(service: BackendAPI, *, fixture_path=None, lease_directory=None, credentials_path=None):
    """Purpose: populate a fresh local database once, in one transaction.

    Inputs: initialized BackendAPI; optional fixture/lease paths for deployment/tests;
    credentials_path defaults beside the DB, named <database-stem>-bootstrap-login.json.
    Outputs: safe summary with status, counts and credential-file path, never passwords.
    Raises: ValueError for corrupt/inconsistent bundled data or credential recovery file;
    OSError for missing assets/private-file creation; sqlite3.Error for storage failure.
    Failures roll back all seeded rows; files created by a failed attempt are removed.
    Existing databases/finished markers return without changing records or credentials.
    """
    database = Path(service.database)
    credentials = resolve_project_path(credentials_path) if credentials_path else database.with_name(database.stem+"-bootstrap-login.json")
    created_credentials = False
    try:
        with closing(service._connect()) as db, db:
            db.execute("PRAGMA secure_delete=ON")
            db.execute("BEGIN IMMEDIATE")
            marker = db.execute("SELECT credentials_path FROM bootstrap_runs WHERE name='fictional-local-v1'").fetchone()
            if marker:
                if credentials_path is None:
                    stored = marker[0]
                    credentials = database.parent / legacy_basename(stored) if is_absolute_reference(stored) else (database.parent / stored).resolve()
                portable = reference(credentials, database.parent)
                if credentials.is_file():
                    before = credentials.read_text(encoding="utf-8")
                    document = _credential_document(json.loads(before), database, credentials, relocating=True)
                    owner_email = document["accounts"][0]["email"]
                    owner = db.execute("SELECT salt,password_hash FROM users WHERE email=?", (owner_email,)).fetchone()
                    if not owner or service._hash_password(document["password"], owner[0]) != owner[1]:
                        raise ValueError("Bootstrap credential file does not match the initialized accounts")
                    after = json.dumps(document, indent=2)+"\n"
                    if after != before:
                        _write_credentials(credentials, after)
                if portable != marker[0]:
                    db.execute("UPDATE bootstrap_runs SET credentials_path=? WHERE name='fictional-local-v1'", (portable,))
                display, base = display_reference(credentials, database.parent)
                return {"status": "already_bootstrapped", "credentialsPath": display, "credentialsBase": base}
            tables = ["users", "sessions", "properties", "leases", "lease_documents", "policies", "requests", "policy_audit"]
            if any(db.execute(f"SELECT 1 FROM {table} LIMIT 1").fetchone() for table in tables):
                return {"status": "existing_database", "credentialsPath": None}
            fixture = json.loads(resolve_project_path(fixture_path or "contracts/bootstrap.json").read_text(encoding="utf-8"))
            if fixture.get("synthetic") is not True or fixture.get("version") != 1:
                raise ValueError("Unsupported or non-synthetic bootstrap snapshot")
            org = fixture["organizationId"]
            users = fixture["users"]
            properties = fixture["properties"]
            leases = fixture["leases"]
            policies = fixture["policies"]
            requests = fixture["requests"]
            ids = lambda rows: {row["id"] for row in rows}
            user_ids, property_ids, lease_ids = ids(users), ids(properties), ids([item["lease"] for item in leases])
            if len(user_ids) != len(users) or len(property_ids) != len(properties) or len(lease_ids) != len(leases):
                raise ValueError("Duplicate bootstrap identity")
            for schema, rows in [("User", users), ("Property", properties), ("Request", requests)]:
                for row in rows:
                    service._validate(schema, row)
            directory = resolve_project_path(lease_directory or "docs/synthetic-leases")
            manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
            documents = {entry["leaseId"]: entry for entry in manifest["documents"]}
            lease_blobs = []
            occupied = set()
            for item in leases:
                lease = item["lease"]
                service._validate("Lease", lease)
                if lease["tenantId"] not in user_ids or lease["propertyId"] not in property_ids:
                    raise ValueError("Invalid bootstrap lease ownership")
                unit = (lease["propertyId"], lease["unit"])
                if unit in occupied:
                    raise ValueError("Duplicate bootstrap occupied unit")
                occupied.add(unit)
                for clause in item["clauses"]:
                    service._validate("Citation", clause)
                    if clause["documentId"] not in lease["documents"]:
                        raise ValueError("Bootstrap citation belongs to a different document")
                entry = documents[lease["id"]]
                pdf_path = (directory / entry["pdf"]).resolve()
                if not pdf_path.is_relative_to(directory.resolve()):
                    raise ValueError("Bootstrap PDF must remain inside the lease directory")
                pdf = pdf_path.read_bytes()
                if entry["documentId"] not in lease["documents"] or hashlib.sha256(pdf).hexdigest() != entry["pdfSha256"] or not pdf.startswith(b"%PDF-"):
                    raise ValueError("Bootstrap lease PDF identity/hash mismatch")
                lease_blobs.append((entry["documentId"], org, lease["id"], entry["pdf"], pdf, entry["pdfSha256"]))
            for request in requests:
                lease = next((item["lease"] for item in leases if item["lease"]["id"] == request["leaseId"]), None)
                if not lease or lease["tenantId"] != request["tenantId"]:
                    raise ValueError("Invalid bootstrap request ownership")
            policy_rows = []
            for policy in policies:
                if policy["propertyId"] and policy["propertyId"] not in property_ids:
                    raise ValueError("Invalid bootstrap policy scope")
                pdf = policy_pdf(policy)
                item = {**policy, "size": len(pdf), "pageCount": None, "status": "uploaded", "excerpt": None,
                        "description": "Synthetic bundled policy PDF; extraction/indexing and review pending.",
                        "compliance": {"status": "pending"}, "contentHash": hashlib.sha256(pdf).hexdigest()}
                previous = next((p for p in policies if p["familyId"] == policy["familyId"] and p["version"] == policy["version"]-1), None)
                item["supersedesId"] = previous["id"] if previous else None
                service._validate("PolicyVersion", item)
                policy_rows.append((item["id"], org, item["familyId"], item["version"], item["effectiveFrom"], item["effectiveTo"],
                                    item["propertyId"], item["state"], item["status"], item["supersedesId"], json.dumps(item), pdf, service.time_zone))
            if credentials.exists():
                recovered = _credential_document(json.loads(credentials.read_text(encoding="utf-8")), database, credentials)
                if (not isinstance(recovered.get("password"), str) or len(recovered["password"]) < 24
                        or recovered.get("accounts") != [{"email": u["email"], "name": u["name"], "role": u["role"]} for u in users]):
                    raise ValueError("Existing bootstrap credential file does not match this installation")
                password = recovered["password"]
                _write_credentials(credentials, json.dumps(recovered, indent=2)+"\n")
            else:
                password = os.getenv("LAGA_BOOTSTRAP_PASSWORD")
                if password is None:
                    password = secrets.token_urlsafe(24)
                elif len(password) < 24 or len(password.encode("utf-8")) > 1024:
                    raise ValueError("LAGA_BOOTSTRAP_PASSWORD must be at least 24 characters and at most 1024 UTF-8 bytes")
            for user in users:
                salt = secrets.token_hex(16)
                db.execute("INSERT INTO users (id,email,profile,salt,password_hash,organization_id) VALUES (?, ?, ?, ?, ?, ?)",
                           (user["id"], user["email"].casefold(), json.dumps(user), salt, service._hash_password(password, salt), org))
            db.executemany("INSERT INTO properties VALUES (?, ?, ?)", [(p["id"], org, json.dumps(p)) for p in properties])
            db.executemany("INSERT INTO leases VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                           [(l["lease"]["id"], org, l["lease"]["tenantId"], l["lease"]["propertyId"], l["lease"]["unit"], l["lease"]["status"], json.dumps(l["lease"]), json.dumps(l["clauses"])) for l in leases])
            db.executemany("INSERT INTO lease_documents VALUES (?, ?, ?, ?, ?, ?)", lease_blobs)
            db.executemany("INSERT INTO policies VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", policy_rows)
            db.executemany("INSERT INTO requests VALUES (?, ?, ?, ?, ?)", [(r["id"], org, r["tenantId"], r["leaseId"], json.dumps(r)) for r in requests])
            if not credentials.exists():
                credentials.parent.mkdir(parents=True, exist_ok=True)
                descriptor = os.open(credentials, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                created_credentials = True
                with os.fdopen(descriptor, "w", encoding="utf-8") as output:
                    json.dump(_credential_document({"synthetic": True, "database": service.database, "password": password,
                               "accounts": [{"email": u["email"], "name": u["name"], "role": u["role"]} for u in users]}, database, credentials), output, indent=2)
                    output.write("\n")
            db.execute("INSERT INTO bootstrap_runs VALUES (?, ?, ?, ?, ?)", ("fictional-local-v1", 1, org, reference(credentials, database.parent), service._timestamp()))
        display, base = display_reference(credentials, database.parent)
        return {"status": "bootstrapped", "credentialsPath": display, "credentialsBase": base, "users": len(users), "properties": len(properties),
                "leases": len(leases), "leaseDocuments": len(lease_blobs), "policies": len(policies), "requests": len(requests)}
    except BaseException:
        if created_credentials:
            credentials.unlink(missing_ok=True)
        raise

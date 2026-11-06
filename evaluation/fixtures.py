"""Real PDF evidence with deliberately simple, deterministic mock selection.

Rules are independent of golden expected IDs. They do not simulate Pinecone
ranking quality. No chunks, page numbers, quotes, or ownership claims are invented.
"""
from contextlib import closing
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import re
import sqlite3

from laga.backend_api import BackendAPI
from lease_rag.chunking import chunk_pdf
from lease_rag.manifest import read_manifest

ROOT = Path(__file__).resolve().parents[1]


class ReadOnlyBackend(BackendAPI):
    """Use the existing authorization methods without constructor/schema writes."""

    def __init__(self, database):
        self.database = str(Path(database).resolve())

    def _connect(self):
        return sqlite3.connect(Path(self.database).as_uri() + "?mode=ro", uri=True)

    def authorize(self, tenant_id, lease_id):
        with closing(self._connect()) as db:
            principal, org = self._principal(
                db, {"id": tenant_id}, role="tenant", permission="lease:read",
            )
            lease, _ = self._lease(db, org, principal, lease_id)
        return principal, org, lease


def mock_backend(directory):
    """Minimal disposable SQLite fixture; real _principal/_lease checks, no login."""
    data = json.loads((ROOT / "contracts/bootstrap.json").read_text())
    if data.get("synthetic") is not True:
        raise ValueError("Only the public synthetic bootstrap fixture is permitted.")
    path = Path(directory) / "evaluation.sqlite3"
    with closing(sqlite3.connect(path)) as db, db:
        db.executescript(
            "CREATE TABLE users(id TEXT, profile TEXT, organization_id TEXT);"
            "CREATE TABLE leases(id TEXT, organization_id TEXT, payload TEXT, clauses TEXT);"
        )
        db.executemany(
            "INSERT INTO users VALUES(?,?,?)",
            [(u["id"], json.dumps(u), data["organizationId"]) for u in data["users"]],
        )
        db.executemany(
            "INSERT INTO leases VALUES(?,?,?,?)",
            [(r["lease"]["id"], data["organizationId"], json.dumps(r["lease"]),
              json.dumps(r["clauses"])) for r in data["leases"]],
        )
    return ReadOnlyBackend(path)


def canonical_documents(source):
    path = ROOT / source["path"]
    if sha256(path.read_bytes()).hexdigest() != source["sha256"]:
        raise ValueError("The annotated PDF has changed; references need re-annotation.")
    records = read_manifest(ROOT / source["manifest"], ROOT / "data")
    record = next(r for r in records if r["document_id"] == source["document_id"])
    documents, _ = chunk_pdf(record["pdf_path"], record, (ROOT / "data").resolve())
    return documents


class FixtureFactory:
    """Scope is checked by SQLite before this factory is given to the graph."""

    RULES = (
        (r"\blate\s+fee\b", ("4", "6")),
        (r"\bNSF\b", ("7",)),
        (r"\bparking\b", ("13",)),
        (r"\bpet", ("11",)),
        (r"\bsmok|\bvaping", ("12",)),
        (r"\butilit|\bservices\b", ("16",)),
        (r"\bsecurity\s+deposit\b", ("5",)),
        (r"\bterm\b|\bstart\b|\bend\b", ("3",)),
        (r"\bmonthly\s+rent\b", ("4",)),
    )

    def __init__(self, documents, trusted):
        self.documents, self.trusted = documents, trusted

    def __call__(self, tenant_id, tenant_name, lease_id):
        if (tenant_id, tenant_name, lease_id) != self.trusted:
            raise PermissionError("Unexpected evaluation scope.")
        return self

    def invoke(self, query):
        # Retries contain a generic prefix. Match only the original question.
        query = query.split("dates, and exceptions: ", 1)[-1]
        sections = next((ids for pattern, ids in self.RULES
                         if re.search(pattern, query, re.I)), ())
        return deepcopy([d for d in self.documents
                         if d.metadata.get("section_id") in sections][:5])

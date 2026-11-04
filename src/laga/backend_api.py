"""The backend team's implementation surface. Operation names match OpenAPI IDs.

SQLite implements account, portfolio, lease, request and policy persistence.
Assistant chat uses LangGraph with explicit server-side retriever injection.
Live retrieval and document ingestion remain external integration tasks.
Keep keyword names aligned with contracts/openapi.json and the UI HTTP gateway.
Authentication uses a local SQLite store. Application startup can bootstrap the bundled fictional dataset.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone, date
from zoneinfo import ZoneInfo
import uuid
from contextlib import closing
from getpass import getpass
import hashlib
import hmac
import json
from pathlib import Path
import secrets
import sqlite3
import time
from typing import Any

from .paths import resolve_project_path

DEFAULT_DATABASE = Path("data/backend.sqlite3")
DTO = dict[str, Any]


class APIError(Exception):
    def __init__(self, status: int, code: str, message: str, fields: dict[str, str] | None = None):
        """Purpose: describe a safe API failure.

        Inputs: HTTP status, stable code, safe message, optional string field messages.
        Outputs: exception carrying status/code/message/fields; no response is sent here.
        Raises: no expected exceptions for valid typed arguments.
        """
        super().__init__(message)
        self.status, self.code, self.message = status, code, message
        self.fields = fields or {}


class BackendAPI:
    """Retain public route method signatures when replacing storage or integrating services.

    `user` is the authenticated, server-owned User DTO. It is never request JSON.
    Business methods must enforce organization/record ownership, not just role.
    Return an unwrapped DTO; the HTTP adapter validates and wraps it as {data: ...}.
    Synchronous methods run in a worker thread so DB work does not block the event loop.
    """

    def __init__(self, database: str | Path, *, session_seconds: int = 28800, now=time.time, time_zone: str = "America/New_York",
                 assistant_retriever_factory=None):
        """Purpose: Initialize persistent account/session and portfolio tables, indexes and additive membership migration.

        Inputs: database: filesystem SQLite path (not :memory:); session_seconds: integer absolute session lifetime from 1 through 2147483647 seconds, default 28800; now: injectable epoch-seconds clock; time_zone: IANA business timezone, default America/New_York; assistant_retriever_factory: optional server-injected tenant/lease-scoped retriever factory, never a browser field. None fails safely without using mocks.

        Outputs: A BackendAPI instance; creates the parent directory and missing tables. No users or synthetic leases are seeded.

        Raises: ValueError for invalid lifetime type/range, blank path or :memory: storage; ZoneInfoNotFoundError for unknown timezone; OSError/sqlite3.Error for inaccessible storage.
        """
        if type(session_seconds) is not int or not 1 <= session_seconds <= 2**31-1:
            raise ValueError("session_seconds must be an integer from 1 through 2147483647")
        if not isinstance(database, (str, Path)) or not str(database).strip() or str(database) == ":memory:":
            raise ValueError("Use a nonempty filesystem database path; requests open separate connections")
        self.database = str(resolve_project_path(database))
        self.session_seconds, self.now = session_seconds, now
        self.time_zone = time_zone
        ZoneInfo(time_zone)
        from .assistant_integration import AssistantIntegration
        self._assistant = AssistantIntegration(
            retriever_factory=assistant_retriever_factory, now=now,
            session_seconds=session_seconds,
        )
        Path(self.database).parent.mkdir(parents=True, exist_ok=True)
        self._dummy_salt = secrets.token_hex(16)
        self._dummy_hash = self._hash_password("nonexistent-account", self._dummy_salt)
        with closing(self._connect()) as db, db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL,
                    profile TEXT NOT NULL, salt TEXT NOT NULL, password_hash TEXT NOT NULL, organization_id TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL,
                    csrf TEXT NOT NULL, expires REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS login_attempts (bucket TEXT NOT NULL, attempted REAL NOT NULL);
                CREATE INDEX IF NOT EXISTS attempts_bucket ON login_attempts(bucket, attempted);
                CREATE TABLE IF NOT EXISTS properties (
                    id TEXT PRIMARY KEY, organization_id TEXT NOT NULL, payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS leases (
                    id TEXT PRIMARY KEY, organization_id TEXT NOT NULL, tenant_id TEXT NOT NULL,
                    property_id TEXT NOT NULL, unit TEXT NOT NULL, status TEXT NOT NULL,
                    payload TEXT NOT NULL, clauses TEXT NOT NULL
                );
                CREATE UNIQUE INDEX IF NOT EXISTS active_unit ON leases(property_id, unit) WHERE status='active';
                CREATE TABLE IF NOT EXISTS requests (
                    id TEXT PRIMARY KEY, organization_id TEXT NOT NULL, tenant_id TEXT NOT NULL,
                    lease_id TEXT NOT NULL, payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS policies (
                    id TEXT PRIMARY KEY, organization_id TEXT NOT NULL, family_id TEXT NOT NULL,
                    version INTEGER NOT NULL, effective_from TEXT NOT NULL, effective_to TEXT,
                    property_id TEXT, state TEXT NOT NULL, status TEXT NOT NULL,
                    supersedes_id TEXT, payload TEXT NOT NULL, file BLOB NOT NULL,
                    time_zone TEXT NOT NULL, UNIQUE(family_id, version)
                );
                CREATE TABLE IF NOT EXISTS bootstrap_runs (
                    name TEXT PRIMARY KEY, version INTEGER NOT NULL, organization_id TEXT NOT NULL,
                    credentials_path TEXT NOT NULL, completed_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS lease_documents (
                    id TEXT PRIMARY KEY, organization_id TEXT NOT NULL, lease_id TEXT NOT NULL,
                    filename TEXT NOT NULL, file BLOB NOT NULL, content_hash TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS policy_audit (
                    id TEXT PRIMARY KEY, organization_id TEXT NOT NULL, event TEXT NOT NULL,
                    payload TEXT NOT NULL, file BLOB NOT NULL, recorded_at TEXT NOT NULL
                );
            """)

            db.execute("BEGIN IMMEDIATE")
            columns = {r[1] for r in db.execute("PRAGMA table_info(users)")}
            if "organization_id" not in columns:
                db.execute("ALTER TABLE users ADD COLUMN organization_id TEXT")

    def _connect(self):
        """Purpose: Open a short-lived SQLite connection.

        Inputs: No arguments beyond self; uses the configured database path and a 10-second busy timeout.

        Outputs: sqlite3.Connection owned by the caller. Use closing(connection) and a transaction context.

        Raises: sqlite3.Error for unavailable or locked storage.
        """
        return sqlite3.connect(self.database, timeout=10)

    @staticmethod
    def _digest(token: str) -> str:
        """Purpose: Produce a one-way identifier for session tokens and rate-limit buckets.

        Inputs: token: server-generated token or internal bucket string; never a password hashing function.

        Outputs: Lowercase 64-character SHA-256 hexadecimal digest. No persistence.

        Raises: No expected domain exceptions for a valid str; encoding/type errors for invalid caller input.
        """
        return hashlib.sha256(token.encode()).hexdigest()

    @staticmethod
    def _hash_password(password: str, salt: str) -> str:
        """Purpose: Derive a salted password verifier with scrypt (N=16384, r=8, p=1, dklen=32).

        Inputs: password: UTF-8 string; salt: hexadecimal random salt. Provision/login enforce password byte limits.

        Outputs: 64-character hexadecimal derived key; never the password.

        Raises: ValueError for malformed salt or scrypt resource limits; MemoryError for exhausted memory.
        """
        return hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1, dklen=32).hex()

    def provision_user(self, *, user: DTO, password: str, organization_id: str) -> None:
        """Purpose: Administratively create a local account with explicit organization membership; never exposed over HTTP.

        Inputs: user: canonical User DTO with nonblank ID/name, a usable email of at most 320 characters, and server-approved role and permissions; password: 12+ characters, at most 1024 UTF-8 bytes; organization_id: nonblank internal organization key. Email is normalized. Tenant lease membership is established by import_lease, not by trusting display fields.

        Outputs: None. Persists the User JSON, normalized email, random salt, scrypt verifier and internal organization key. Existing IDs/emails are never overwritten.

        Raises: APIError 422 VALIDATION_ERROR for invalid User DTO; ValueError for invalid password/email/ID/name/organization; sqlite3.IntegrityError for duplicate ID/email; other storage errors propagate to administrative caller.
        """
        from .api import load_contract, validate
        validate(load_contract(), {"$ref": "#/components/schemas/User"}, user)
        if not isinstance(password, str) or len(password) < 12 or len(password.encode()) > 1024:
            raise ValueError("Use a password of at least 12 characters and at most 1024 UTF-8 bytes")
        user = dict(user)
        user["email"] = user["email"].strip().casefold()
        if (not user["id"].strip() or not user["name"].strip() or len(user["email"]) > 320
                or user["email"].count("@") != 1 or any(c.isspace() for c in user["email"])
                or not all(user["email"].split("@"))):
            raise ValueError("Use a nonblank ID/name and a usable email of at most 320 characters")
        if not isinstance(organization_id, str) or not organization_id.strip():
            raise ValueError("An explicit internal organization ID is required")
        salt = secrets.token_hex(16)
        password_hash = self._hash_password(password, salt)
        with closing(self._connect()) as db, db:
            db.execute("INSERT INTO users (id,email,profile,salt,password_hash,organization_id) VALUES (?, ?, ?, ?, ?, ?)",
                       (user["id"], user["email"], json.dumps(user), salt, password_hash, organization_id))

    def post_auth_login(self, *, email: str, password: str, session_token: str | None,
                        client_key: str) -> tuple[DTO, str]:
        """Purpose: Authenticate a locally provisioned account, rotate its browser session and return session metadata.

        Inputs: email/password: LoginInput fields; session_token: existing browser cookie or None; client_key: trusted peer address from transport. Role/permissions never come from request fields. Rate limit: 10 attempts per account and peer in a rolling 15-minute window, including successes.

        Outputs: (Session DTO, new raw cookie token). Session has user and csrfToken. Only the HTTP adapter places the raw token in an HttpOnly cookie; DB stores its digest. Previous browser token is revoked on successful login; lifetime is absolute.

        Raises: APIError 401 INVALID_CREDENTIALS for unknown account, wrong/empty/oversized credentials; 429 RATE_LIMITED when either bucket is full; storage/hash errors propagate and HTTP maps them to safe 503.
        """
        email = email.strip().casefold()
        if not email or len(email) > 320 or len(password.encode()) > 1024 or not password:
            raise APIError(401, "INVALID_CREDENTIALS", "Email or password is incorrect.")
        now = self.now()
        # Separate account and peer buckets prevent brute force distributed across accounts/IPs.
        buckets = [self._digest("account:" + email), self._digest("peer:" + client_key)]
        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM login_attempts WHERE attempted <= ?", (now-900,))
            for bucket in buckets:
                count = db.execute("SELECT COUNT(*) FROM login_attempts WHERE bucket=?", (bucket,)).fetchone()[0]
                if count >= 10:
                    raise APIError(429, "RATE_LIMITED", "Too many sign-in attempts. Try again later.")
            db.executemany("INSERT INTO login_attempts VALUES (?, ?)", [(b, now) for b in buckets])
            row = db.execute("SELECT id, profile, salt, password_hash FROM users WHERE email=?", (email,)).fetchone()
        salt, expected = (row[2], row[3]) if row else (self._dummy_salt, self._dummy_hash)
        valid = hmac.compare_digest(self._hash_password(password, salt), expected)
        if not row or not valid:
            raise APIError(401, "INVALID_CREDENTIALS", "Email or password is incorrect.")
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        with closing(self._connect()) as db, db:
            db.execute("DELETE FROM sessions WHERE expires <= ?", (now,))
            if session_token:
                db.execute("DELETE FROM sessions WHERE token_hash=?", (self._digest(session_token),))
            db.execute("INSERT INTO sessions VALUES (?, ?, ?, ?)",
                       (self._digest(token), row[0], csrf, now+self.session_seconds))
        return {"user": json.loads(row[1]), "csrfToken": csrf}, token

    def get_auth_session(self, *, session_token: str | None) -> DTO:
        """Purpose: Resolve an unexpired session using current server-side account data.

        Inputs: session_token: raw cookie string or None. Tokens longer than 128 characters are treated as anonymous.

        Outputs: Session DTO: {user: User, csrfToken: str}; missing, revoked or expired tokens return {user: None, csrfToken: None}. Removes expired session rows without extending expiry.

        Raises: No 401 for anonymous sessions. sqlite3.Error on storage failure (HTTP 503).
        """
        if not session_token or len(session_token) > 128:
            return {"user": None, "csrfToken": None}
        with closing(self._connect()) as db, db:
            db.execute("DELETE FROM sessions WHERE expires <= ?", (self.now(),))
            row = db.execute("SELECT u.profile, s.csrf FROM sessions s JOIN users u ON u.id=s.user_id "
                             "WHERE s.token_hash=?", (self._digest(session_token),)).fetchone()
        return {"user": json.loads(row[0]), "csrfToken": row[1]} if row else {"user": None, "csrfToken": None}

    def post_auth_logout(self, *, session_token: str | None) -> DTO:
        """Purpose: Revoke the supplied session token.

        Inputs: session_token: raw cookie or None. HTTP transport requires an authenticated session, allowed Origin and matching CSRF before calling this method; direct calls are internal.

        Outputs: Logout DTO {signedOut: True}; HTTP clears the matching cookie. Internal revocation is idempotent even for unknown tokens.

        Raises: sqlite3.Error for storage failure. HTTP guards can return 401/403 before this method executes.
        """
        if session_token:
            with closing(self._connect()) as db, db:
                db.execute("DELETE FROM sessions WHERE token_hash=?", (self._digest(session_token),))
        return {"signedOut": True}

    @staticmethod
    def _todo(operation: str, *, inputs: DTO | None = None) -> DTO:
        """Purpose: Fail explicitly when an external backend capability is not connected.

        Inputs: operation: internal operation name; inputs: reserved optional arguments.

        Outputs: No response data; unavailable capabilities fail explicitly.

        Raises: APIError 503 BACKEND_NOT_IMPLEMENTED.
        """
        raise APIError(503, "BACKEND_NOT_IMPLEMENTED", f"Backend implementation pending: {operation}.")

    def get_user_id(self, *, session_token: str | None) -> str:
        """Purpose: Return the authenticated user ID without accepting a client-selected identity.

        Inputs: session_token: current raw session cookie or None. Internal helper, not an additional public HTTP route.

        Outputs: Stable User.id string from get_auth_session.

        Raises: APIError 401 UNAUTHENTICATED for missing/revoked/expired sessions; sqlite3.Error for storage failure.
        """
        user = self.get_auth_session(session_token=session_token)["user"]
        if user is None:
            raise APIError(401, "UNAUTHENTICATED", "Please sign in to continue.")
        return user["id"]

    def _principal(self, db, user: DTO, *, role: str | None = None, permission: str | None = None):
        """Purpose: Re-read the authoritative account and organization for a service operation.

        Inputs: db: open connection; user: transport-authenticated User DTO whose id is looked up again; role/permission: optional required server role and permission. Do not expose this direct-call boundary to untrusted callers.

        Outputs: (current User DTO, internal organization_id). Caller-supplied role/permissions/organization are ignored.

        Raises: APIError 401 UNAUTHENTICATED for missing account; 403 FORBIDDEN for missing organization membership or role/permission mismatch; sqlite3.Error.
        """
        row = db.execute("SELECT profile, organization_id FROM users WHERE id=?", (user.get("id"),)).fetchone()
        if not row:
            raise APIError(401, "UNAUTHENTICATED", "Please sign in to continue.")
        current = json.loads(row[0])
        if not row[1] or (role and current["role"] != role) or (permission and permission not in current["permissions"]):
            raise APIError(403, "FORBIDDEN", "Your account cannot perform this action.")
        return current, row[1]

    def _today(self, time_zone: str | None = None) -> str:
        """Purpose: Compute the current business calendar date independently of host timezone.

        Inputs: time_zone: optional immutable policy-family IANA timezone; defaults to instance time_zone; uses injected clock.

        Outputs: ISO YYYY-MM-DD string.

        Raises: ZoneInfoNotFoundError for unknown timezone; ValueError/OverflowError for invalid clock values.
        """
        return datetime.fromtimestamp(self.now(), ZoneInfo(time_zone or self.time_zone)).date().isoformat()

    def _timestamp(self) -> str:
        """Purpose: Create a UTC timestamp for persisted events.

        Inputs: No explicit input; uses the injected epoch clock.

        Outputs: Offset-aware ISO timestamp string in UTC.

        Raises: ValueError/OverflowError for invalid clock values.
        """
        return datetime.fromtimestamp(self.now(), timezone.utc).isoformat()

    @staticmethod
    def _validate(schema: str, value: DTO):
        """Purpose: Validate a DTO against the canonical OpenAPI component schema.

        Inputs: schema: component name, e.g. PolicyUpload; value: JSON-compatible dictionary. Reads contracts/openapi.json or LAGA_CONTRACT_PATH.

        Outputs: None when valid; does not persist or sanitize data.

        Raises: APIError 422 VALIDATION_ERROR with safe field messages for schema, unsafe integers or malformed text; 400 INVALID_JSON for nesting beyond 64 levels; OSError/JSONDecodeError for unavailable/broken contract; schema configuration errors for invalid references.
        """
        from .api import load_contract, validate
        validate(load_contract(), {"$ref": "#/components/schemas/"+schema}, value)

    @staticmethod
    def _lease(db, organization_id: str, user: DTO, id: str):
        """Purpose: Load a lease while concealing foreign-organization and foreign-tenant records.

        Inputs: db: connection; organization_id: authoritative membership; user: server principal; id: opaque lease ID.

        Outputs: (Lease DTO, list of Citation DTOs). Landlords remain organization-scoped; tenants must own the lease.

        Raises: APIError 404 NOT_FOUND for missing or invisible lease; sqlite3.Error/JSONDecodeError for corrupt storage.
        """
        row = db.execute("SELECT payload, clauses FROM leases WHERE id=? AND organization_id=?", (id, organization_id)).fetchone()
        if not row or (user["role"] == "tenant" and json.loads(row[0])["tenantId"] != user["id"]):
            raise APIError(404, "NOT_FOUND", "Lease not found.")
        return json.loads(row[0]), json.loads(row[1])

    def get_workspace(self, *, user: DTO) -> DTO:
        """Purpose: Return one consistent SQLite-backed workspace for the authenticated principal.

        Inputs: user: authenticated User DTO. No client organization, tenant selector or business date is accepted.

        Outputs: Workspace DTO with demo=True for the bootstrapped fictional organization (False otherwise), asOf, timeZone, current user, properties, leases, tenants, requests, policy metadata and summary. Tenant records are filtered to their leases; landlord records to organization. Monetary sums are integer cents over active leases; occupied counts unique property/unit pairs; renewals count active leases ending in 0-90 days. PDF bytes and credential hashes are excluded.

        Raises: APIError 401/403 via _principal; sqlite3.Error or malformed stored JSON/date errors on corrupt storage (safe HTTP 503).
        """
        with closing(self._connect()) as db, db:
            db.execute("BEGIN")
            current, org = self._principal(db, user)
            landlord = current["role"] == "landlord"
            lease_rows = db.execute("SELECT payload FROM leases WHERE organization_id=?" +
                                    ("" if landlord else " AND tenant_id=?"), (org,) if landlord else (org, current["id"])).fetchall()
            leases = [json.loads(r[0]) for r in lease_rows]
            property_ids = {l["propertyId"] for l in leases}
            properties = [json.loads(r[0]) for r in db.execute("SELECT payload FROM properties WHERE organization_id=? ORDER BY id", (org,))]
            if not landlord:
                properties = [p for p in properties if p["id"] in property_ids]
            tenants = [json.loads(r[0]) for r in db.execute("SELECT profile FROM users WHERE organization_id=? ORDER BY id", (org,))]
            tenants = [t for t in tenants if t["role"] == "tenant" and (landlord or t["id"] == current["id"])]
            requests = [json.loads(r[0]) for r in db.execute("SELECT payload FROM requests WHERE organization_id=? ORDER BY rowid DESC", (org,))]
            if not landlord:
                requests = [r for r in requests if r["tenantId"] == current["id"] and r["leaseId"] in {l["id"] for l in leases}]
            policies = [json.loads(r[0]) for r in db.execute("SELECT payload FROM policies WHERE organization_id=? ORDER BY family_id, version DESC", (org,))]
            if not landlord:
                policies = [p for p in policies if p["propertyId"] is None or p["propertyId"] in property_ids]
            today = self._today()
            active = [l for l in leases if l["status"] == "active"]
            summary = {"properties": len(properties), "units": sum(p["units"] for p in properties),
                       "occupied": len({(l["propertyId"], l["unit"]) for l in active}),
                       "monthlyRent": sum(l["rent"] for l in active),
                       "outstandingRent": sum(l["rent"] for l in active if l["paymentStatus"] == "due"),
                       "renewals": sum(0 <= (date.fromisoformat(l["endDate"])-date.fromisoformat(today)).days <= 90 for l in active)}
            seeded = db.execute("SELECT 1 FROM bootstrap_runs WHERE organization_id=?", (org,)).fetchone()
            return {"demo": bool(seeded), "asOf": today, "timeZone": self.time_zone, "user": current,
                    "properties": properties, "leases": leases, "tenants": tenants, "requests": requests,
                    "policies": policies, "summary": summary}

    def get_leases_id(self, *, user: DTO, id: str) -> DTO:
        """Purpose: Return an authorized lease, property, tenant and source excerpts.

        Inputs: user: authenticated User DTO; id: opaque lease ID. Requires lease:read for tenants or leases:read for landlords.

        Outputs: LeaseDetail DTO with lease, property, tenant and clauses. No fabricated citations or automatic sample ingestion.

        Raises: APIError 401/403 for account/permission issues; 404 NOT_FOUND for missing/invisible lease; 503 DATA_INTEGRITY_ERROR if referenced property/tenant is missing; storage errors.
        """
        with closing(self._connect()) as db, db:
            db.execute("BEGIN")
            current, org = self._principal(db, user)
            permission = "lease:read" if current["role"] == "tenant" else "leases:read"
            if permission not in current["permissions"]:
                raise APIError(403, "FORBIDDEN", "Lease access is restricted.")
            lease, clauses = self._lease(db, org, current, id)
            property = db.execute("SELECT payload FROM properties WHERE id=? AND organization_id=?", (lease["propertyId"], org)).fetchone()
            tenant = db.execute("SELECT profile FROM users WHERE id=? AND organization_id=?", (lease["tenantId"], org)).fetchone()
            if not property or not tenant:
                raise APIError(503, "DATA_INTEGRITY_ERROR", "The lease record needs administrative review.")
            return {"lease": lease, "clauses": clauses, "property": json.loads(property[0]), "tenant": json.loads(tenant[0])}

    def create_property(self, *, user: DTO, name: str, address: str, city: str, state: str, units: int) -> DTO:
        """Purpose: Persist an NC property owned by the authenticated landlord organization.

        Inputs: user: authenticated landlord with policies:write; name (1-120), address (1-250), city (1-120): nonblank strings; state: NC; units: integer 1-10000. No organization or property ID is accepted from the client.

        Outputs: Property DTO with generated UUID, trimmed text, immutable NC state, style=willow, empty amenities/description. Writes one row; no lease or occupancy is created.

        Raises: APIError 422 VALIDATION_ERROR for schema/blank fields; 401/403 for principal/permission issues; sqlite3.Error.
        """
        values = {"name": name, "address": address, "city": city, "state": state, "units": units}
        self._validate("PropertyRegistration", values)
        if not all(v.strip() for v in [name, address, city]):
            raise APIError(422, "VALIDATION_ERROR", "Property fields must not be blank.")
        item = {"id": str(uuid.uuid4()), **values, "name": name.strip(), "address": address.strip(),
                "city": city.strip(), "style": "willow", "amenities": [], "description": ""}
        with closing(self._connect()) as db, db:
            _, org = self._principal(db, user, role="landlord", permission="policies:write")
            db.execute("INSERT INTO properties VALUES (?, ?, ?)", (item["id"], org, json.dumps(item)))
        return item

    def import_lease(self, *, organization_id: str, lease: DTO, clauses: list[DTO]) -> None:
        """Purpose: Administratively import a lease with exact citations into the correct organization.

        Inputs: organization_id: internal membership key; lease: canonical Lease DTO referencing an existing tenant and property in that organization; clauses: Citation DTO list whose documentIds belong to lease.documents. No HTTP route. Dates must be real and ordered; rent/deposit nonnegative JavaScript-safe integer cents; dueDay is 1-31 and noticeDays is nonnegative. Active portfolio rent must also remain JavaScript-safe.

        Outputs: None. Inserts a lease and clauses atomically. Enforces one active lease per property/unit and property capacity. Does not modify account profile fields or seed synthetic data automatically.

        Raises: APIError 422 for schema, date, amount, name or citation mismatch; 404 for missing/foreign tenant or property; 409 VERSION_CONFLICT for duplicate ID, active unit or capacity; sqlite3.Error.
        """
        self._validate("Lease", lease)
        for citation in clauses:
            self._validate("Citation", citation)
            if citation["documentId"] not in lease.get("documents", []):
                raise APIError(422, "VALIDATION_ERROR", "Citations must reference this lease's documents.")
        try:
            start, end = date.fromisoformat(lease["startDate"]), date.fromisoformat(lease["endDate"])
            if (start > end or lease["rent"] < 0 or lease["deposit"] < 0
                    or not 1 <= lease["dueDay"] <= 31 or lease["noticeDays"] < 0
                    or not lease["unit"].strip() or not lease["id"].strip()):
                raise ValueError()
        except ValueError:
            raise APIError(422, "VALIDATION_ERROR", "Invalid lease dates or amounts.")
        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            property = db.execute("SELECT payload FROM properties WHERE id=? AND organization_id=?", (lease["propertyId"], organization_id)).fetchone()
            tenant = db.execute("SELECT profile FROM users WHERE id=? AND organization_id=?", (lease["tenantId"], organization_id)).fetchone()
            if not property or not tenant or json.loads(tenant[0])["role"] != "tenant":
                raise APIError(404, "NOT_FOUND", "Property or tenant not found in this organization.")
            if lease["tenantName"] != json.loads(tenant[0])["name"]:
                raise APIError(422, "VALIDATION_ERROR", "Lease tenant name must match the account.")
            if lease["status"] == "active":
                total = sum(json.loads(r[0])["rent"] for r in db.execute("SELECT payload FROM leases WHERE organization_id=? AND status='active'", (organization_id,)))
                if total+lease["rent"] > 2**53-1:
                    raise APIError(422, "VALIDATION_ERROR", "Portfolio rent exceeds the exact integer range supported by the UI.")
            occupied = db.execute("SELECT COUNT(*) FROM leases WHERE property_id=? AND status='active'", (lease["propertyId"],)).fetchone()[0]
            if lease["status"] == "active" and occupied >= json.loads(property[0])["units"]:
                raise APIError(409, "VERSION_CONFLICT", "The property has no unoccupied units.")
            try:
                db.execute("INSERT INTO leases VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                           (lease["id"], organization_id, lease["tenantId"], lease["propertyId"], lease["unit"], lease["status"], json.dumps(lease), json.dumps(clauses)))
            except sqlite3.IntegrityError:
                raise APIError(409, "VERSION_CONFLICT", "Lease ID or active unit already exists.")

    def post_assistant_messages(self, *, user: DTO, question: str, scope: DTO, asOf: str,
                                threadId: str | None = None) -> DTO:
        """Purpose: Answer an authenticated tenant's authorized lease question using LangGraph.

        Inputs: user: transport-authenticated User re-read by _principal; question: 1-2000 characters; scope: tenant lease scope only; asOf: real ISO calendar date; threadId: optional conversation owned by this principal, organization, lease and session. Internal callers have a separate thread namespace.

        Outputs: OpenAPI-validated Answer DTO with grounded citations, integer-cent calculations, unavailable compliance, and an ephemeral process-local thread ID. No mock fallback, transcript persistence, or SQLite schema changes.

        Raises: APIError 401/403 for invalid principal/tenant permissions; 422 UNSUPPORTED_SCOPE for portfolio or validation errors; 404 for invisible lease/thread; 503 RAG_UNAVAILABLE, ASSISTANT_UNAVAILABLE or BACKEND_CONTRACT_ERROR; 429 for thread capacity; SQLite storage errors.
        """
        with closing(self._connect()) as db:
            current, org = self._principal(db, user if isinstance(user, dict) else {})
            self._validate("AskInput", {
                "question": question, "scope": scope, "asOf": asOf, "threadId": threadId,
            })
            if scope["type"] != "lease":
                raise APIError(422, "UNSUPPORTED_SCOPE", "Assistant chat supports tenant lease scope only.")
            if current["role"] != "tenant" or "lease:read" not in current["permissions"]:
                raise APIError(403, "FORBIDDEN", "Assistant chat is available to authorized tenants only.")
            if not scope["id"] or not scope["id"].strip():
                raise APIError(422, "VALIDATION_ERROR", "Choose a valid lease.")
            lease, _ = self._lease(db, org, current, scope["id"])
        return self._assistant.answer(
            principal=current, organization_id=org, lease=lease, question=question,
            as_of=asOf, thread_id=threadId,
            validate_response=lambda response: self._validate("Answer", response),
        )

    def post_requests(self, *, user: DTO, leaseId: str, category: str, subject: str, message: str) -> DTO:
        """Purpose: Persist a tenant clarification request for an owned lease.

        Inputs: user: authenticated tenant with requests:create; leaseId: owned lease ID; category: string; subject: nonblank 1-120 characters; message: nonblank 1-5000 characters.

        Outputs: Request DTO with generated ID, server tenantId, leaseId, trimmed subject/message, status=open, UTC createdAt and reply=None.

        Raises: APIError 422 VALIDATION_ERROR for invalid/blank content; 401/403 for principal/role/permission; 404 NOT_FOUND for missing/invisible lease; sqlite3.Error.
        """
        self._validate("RequestInput", {"leaseId": leaseId, "category": category, "subject": subject, "message": message})
        if not subject.strip() or not message.strip():
            raise APIError(422, "VALIDATION_ERROR", "Subject and message must not be blank.")
        with closing(self._connect()) as db, db:
            current, org = self._principal(db, user, role="tenant", permission="requests:create")
            self._lease(db, org, current, leaseId)
            item = {"id": str(uuid.uuid4()), "tenantId": current["id"], "leaseId": leaseId, "category": category,
                    "subject": subject.strip(), "message": message.strip(), "status": "open", "createdAt": self._timestamp(), "reply": None}
            db.execute("INSERT INTO requests VALUES (?, ?, ?, ?, ?)", (item["id"], org, current["id"], leaseId, json.dumps(item)))
        return item

    def post_requests_id_reply(self, *, user: DTO, id: str, reply: str) -> DTO:
        """Purpose: Save a landlord reply to an organization-owned request.

        Inputs: user: authenticated landlord with requests:write; id: opaque request ID; reply: nonblank 1-5000 characters. Repeated replies replace the current reply; threaded history is a backend TODO.

        Outputs: Updated Request DTO with trimmed reply and status=answered; updates one row inside a transaction.

        Raises: APIError 422 VALIDATION_ERROR for reply; 401/403 for principal/permission; 404 NOT_FOUND for missing/foreign request; sqlite3.Error.
        """
        self._validate("ReplyInput", {"reply": reply})
        if not reply.strip():
            raise APIError(422, "VALIDATION_ERROR", "Reply must not be blank.")
        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            _, org = self._principal(db, user, role="landlord", permission="requests:write")
            row = db.execute("SELECT payload FROM requests WHERE id=? AND organization_id=?", (id, org)).fetchone()
            if not row:
                raise APIError(404, "NOT_FOUND", "Request not found.")
            item = json.loads(row[0])
            item.update(reply=reply.strip(), status="answered")
            db.execute("UPDATE requests SET payload=? WHERE id=?", (json.dumps(item), id))
        return item

    def post_policies(self, *, user: DTO, file: bytes, filename: str, content_type: str,
                      state: str, effectiveFrom: str, familyId: str | None = None,
                      expectedVersion: int | None = None, title: str | None = None,
                      category: str | None = None, propertyId: str | None = None) -> DTO:
        """Purpose: Store PDF bytes privately and append version metadata in a single serialized transaction.

        Inputs: user: authenticated landlord with policies:write; file: PDF bytes, nonempty and <=10 MiB; filename: untrusted .pdf display name; content_type: application/pdf or application/octet-stream; state: NC; effectiveFrom: real calendar date. New family: title and category required, optional propertyId. Existing family: familyId and expectedVersion required; title/category/propertyId/state must agree if supplied. Effective date must be >= business today and strictly later than latest version start. Inherits immutable family timezone.

        Outputs: PolicyVersion DTO with generated revision/family UUIDs, version, interval, supersedesId, upload timestamp, safe basename, byte size, SHA-256 contentHash, status=uploaded, pageCount/excerpt=None and compliance=pending. PDF bytes remain a SQLite BLOB; previous effectiveTo becomes new start atomically. This method does not parse, scan, index, review or mark a file ready.

        Raises: APIError 401/403 for account/permission; 404 NOT_FOUND for missing/foreign property/family; 409 VERSION_CONFLICT for stale expectedVersion or invalid chronological append; 413 INVALID_FILE_SIZE for oversize; 422 for empty file, invalid PDF header/type/name, schema/date/state or changed family fields; sqlite3.Error. All transaction failures roll back.
        """
        values = {"file": filename, "state": state, "effectiveFrom": effectiveFrom}
        values.update({k: v for k, v in {"familyId": familyId, "expectedVersion": expectedVersion, "title": title, "category": category, "propertyId": propertyId}.items() if v is not None})
        self._validate("PolicyUpload", values)
        if any(isinstance(v, str) and not v.strip() for v in [familyId, propertyId, title, category]):
            raise APIError(422, "VALIDATION_ERROR", "Policy identifiers and supplied text must not be blank.")
        if not file or len(file) > 10*1024*1024:
            raise APIError(413 if file else 422, "INVALID_FILE_SIZE", "PDFs must be nonempty and at most 10 MiB.")
        if not file.startswith(b"%PDF-") or not filename.lower().endswith(".pdf") or content_type not in {"application/pdf", "application/octet-stream"}:
            raise APIError(422, "INVALID_PDF", "Choose a file with a PDF name, type and header.")
        try:
            if date.fromisoformat(effectiveFrom).isoformat() != effectiveFrom:
                raise ValueError()
        except ValueError:
            raise APIError(422, "VALIDATION_ERROR", "Enter a real ISO effective date.")
        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            current, org = self._principal(db, user, role="landlord", permission="policies:write")
            previous = None
            zone = self.time_zone
            if familyId:
                row = db.execute("SELECT payload, time_zone FROM policies WHERE family_id=? AND organization_id=? ORDER BY version DESC LIMIT 1", (familyId, org)).fetchone()
                if not row:
                    raise APIError(404, "NOT_FOUND", "Policy family not found.")
                previous, zone = json.loads(row[0]), row[1]
                if expectedVersion != previous["version"]:
                    raise APIError(409, "VERSION_CONFLICT", "This policy changed. Refresh before adding a version.")
                if any(v is not None and v != previous[k] for k, v in {"title": title, "category": category, "propertyId": propertyId, "state": state}.items()):
                    raise APIError(422, "VALIDATION_ERROR", "A policy family's title, category, scope and state cannot change.")
                title, category, propertyId = previous["title"], previous["category"], previous["propertyId"]
            elif not title or not title.strip():
                raise APIError(422, "VALIDATION_ERROR", "Give this policy a title.")
            if effectiveFrom < self._today(zone) or (previous and effectiveFrom <= previous["effectiveFrom"]):
                raise APIError(409, "VERSION_CONFLICT", "Use today or a later date, strictly after the latest version's start.")
            targets = [json.loads(r[0]) for r in db.execute("SELECT payload FROM properties WHERE organization_id=?" + (" AND id=?" if propertyId else ""), (org, propertyId) if propertyId else (org,))]
            if propertyId and not targets:
                raise APIError(404, "NOT_FOUND", "Property not found.")
            if state != "NC" or any(p["state"] != state for p in targets):
                raise APIError(422, "VALIDATION_ERROR", "Policy state must match its properties.")
            item = {"id": str(uuid.uuid4()), "familyId": familyId or str(uuid.uuid4()), "title": title.strip(),
                    "name": filename.replace("\\", "/").rsplit("/", 1)[-1], "category": category, "propertyId": propertyId,
                    "status": "uploaded", "version": previous["version"]+1 if previous else 1,
                    "effectiveFrom": effectiveFrom, "effectiveTo": None, "supersedesId": previous["id"] if previous else None,
                    "uploadedAt": self._timestamp(), "size": len(file), "pageCount": None, "uploadedBy": current["name"],
                    "description": "Stored privately; extraction and indexing are pending.", "excerpt": None,
                    "state": state, "compliance": {"status": "pending"}, "contentHash": hashlib.sha256(file).hexdigest()}
            if previous:
                previous["effectiveTo"] = effectiveFrom
                db.execute("UPDATE policies SET effective_to=?, payload=? WHERE id=?", (effectiveFrom, json.dumps(previous), previous["id"]))
            db.execute("INSERT INTO policies VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                       (item["id"], org, item["familyId"], item["version"], effectiveFrom, None, propertyId, state,
                        item["status"], item["supersedesId"], json.dumps(item), file, zone))
        return item

    def delete_policies_id(self, *, user: DTO, id: str) -> DTO:
        """Purpose: Cancel the latest future non-ready policy revision without erasing its audit evidence.

        Inputs: user: authenticated landlord with policies:write; id: opaque policy revision ID. Cancellation is allowed only when effectiveFrom > business today, status != ready, and no successor exists.

        Outputs: Deleted DTO {deleted: True}. Restores predecessor effectiveTo=None, records canceled metadata/PDF bytes in private policy_audit, then removes the revision from the active policy list atomically. A later cancellation retry returns 404.

        Raises: APIError 401/403 for account/permission; 404 NOT_FOUND for missing/foreign revision; 409 VERSION_CONFLICT for effective/ready/nonlatest revision; 503 DATA_INTEGRITY_ERROR for missing predecessor; sqlite3.Error. Rollback preserves original history on failure.
        """
        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            _, org = self._principal(db, user, role="landlord", permission="policies:write")
            row = db.execute("SELECT payload, file, time_zone FROM policies WHERE id=? AND organization_id=?", (id, org)).fetchone()
            if not row:
                raise APIError(404, "NOT_FOUND", "Policy not found.")
            item, data, zone = json.loads(row[0]), row[1], row[2]
            successor = db.execute("SELECT 1 FROM policies WHERE supersedes_id=?", (id,)).fetchone()
            if item["effectiveFrom"] <= self._today(zone) or item["status"] == "ready" or successor:
                raise APIError(409, "VERSION_CONFLICT", "Only the latest future non-ready policy can be canceled.")
            if item["supersedesId"]:
                predecessor = db.execute("SELECT payload FROM policies WHERE id=? AND organization_id=?", (item["supersedesId"], org)).fetchone()
                if not predecessor:
                    raise APIError(503, "DATA_INTEGRITY_ERROR", "The policy history needs administrative review.")
                previous = json.loads(predecessor[0])
                previous["effectiveTo"] = None
                db.execute("UPDATE policies SET effective_to=NULL, payload=? WHERE id=?", (json.dumps(previous), previous["id"]))
            db.execute("INSERT INTO policy_audit VALUES (?, ?, ?, ?, ?, ?)", (id, org, "canceled", json.dumps(item), data, self._timestamp()))
            db.execute("DELETE FROM policies WHERE id=?", (id,))
        return {"deleted": True}


def main():
    parser = argparse.ArgumentParser(description="Provision one local API account (no public registration)")
    parser.add_argument("--database", default=str(DEFAULT_DATABASE))
    parser.add_argument("--organization-id", required=True, help="Internal organization membership ID, not a display name")
    parser.add_argument("--profile", required=True, type=Path, help="User DTO JSON; server-controlled role/permissions")
    args = parser.parse_args()
    password = getpass("Password (12+ characters): ")
    if password != getpass("Confirm password: "):
        parser.error("Passwords do not match")
    BackendAPI(args.database).provision_user(user=json.loads(args.profile.read_text(encoding="utf-8")), password=password, organization_id=args.organization_id)
    print("Account provisioned. No session or password was printed.")


if __name__ == "__main__":
    main()

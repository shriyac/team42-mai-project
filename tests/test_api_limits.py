"""Three-loop regression cases: local bootstrap, boundaries and hostile input."""
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
import json
import os
import subprocess
from datetime import date, timedelta
import inspect
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from fastapi.testclient import TestClient
from laga.api import create_app
from laga.backend_api import APIError, BackendAPI

PROFILE = {"id": "local-owner", "name": "Local Owner", "email": "owner@example.test", "role": "landlord", "permissions": ["portfolio:read", "leases:read", "policies:write", "requests:write"]}
PASSWORD = "local-password-123"
ORIGIN = "https://local-ui.test"


class LocalBootstrapTests(unittest.TestCase):
    def test_first_execution_is_independent_empty_and_restart_is_nondestructive(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = [Path(directory) / dev / "data/backend.sqlite3" for dev in ["developer-a", "developer-b"]]
            first, second = [BackendAPI(p) for p in paths]
            for path in paths:
                with closing(sqlite3.connect(path)) as db:
                    for table in ["users", "sessions", "properties", "leases", "requests", "policies", "policy_audit"]:
                        self.assertEqual(db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], 0)
            first.provision_user(user=PROFILE, password=PASSWORD, organization_id="local-org")
            first.create_property(user=PROFILE, name="Local House", address="1 Test Road", city="Raleigh", state="NC", units=1)
            second.provision_user(user=PROFILE, password=PASSWORD, organization_id="local-org")
            self.assertEqual(second.get_workspace(user=PROFILE)["properties"], [])
            restarted = BackendAPI(paths[0])
            self.assertEqual(len(restarted.get_workspace(user=PROFILE)["properties"]), 1)
            self.assertEqual(restarted.get_workspace(user=PROFILE)["leases"], [])

    def test_default_path_is_independent_of_the_launch_directory(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run([sys.executable, "-c", "from laga.backend_api import DEFAULT_DATABASE; from laga.paths import resolve_project_path; print(resolve_project_path(DEFAULT_DATABASE))"], cwd=directory, env={**os.environ, "PYTHONPATH": str(root / "src")}, capture_output=True, text=True, check=True)
        self.assertEqual(Path(result.stdout.strip()), root / "data/backend.sqlite3")

    def test_concurrent_startup_migrates_legacy_store_once(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "legacy.sqlite3"
            with closing(sqlite3.connect(path)) as db, db:
                db.execute("CREATE TABLE users (id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL, profile TEXT NOT NULL, salt TEXT NOT NULL, password_hash TEXT NOT NULL)")
            with ThreadPoolExecutor(max_workers=4) as pool:
                stores = list(pool.map(lambda _: BackendAPI(path), range(4)))
            self.assertEqual(len(stores), 4)
            with closing(sqlite3.connect(path)) as db:
                columns = [r[1] for r in db.execute("PRAGMA table_info(users)")]
            self.assertEqual(columns.count("organization_id"), 1)

    def test_provisioning_rejects_unusable_identity_before_persisting(self):
        with tempfile.TemporaryDirectory() as directory:
            service = BackendAPI(Path(directory) / "db.sqlite3")
            for field, value in [("email", "x"*321+"@example.test"), ("email", "not-an-email"), ("id", "   "), ("name", "   ")]:
                with self.subTest(field=field, value=value[:30]):
                    with self.assertRaises((ValueError, APIError)):
                        service.provision_user(user={**PROFILE, field: value}, password=PASSWORD, organization_id="local-org")
            with closing(sqlite3.connect(service.database)) as db:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM users").fetchone()[0], 0)


    def test_extreme_configuration_values_fail_before_database_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "never-created.sqlite3"
            for duration in [True, 1.5, float("nan"), float("inf"), "60", 0, -1, 2**53]:
                with self.subTest(duration=duration):
                    with self.assertRaises(ValueError):
                        BackendAPI(path, session_seconds=duration)
            self.assertFalse(path.exists())
            for path in ["", "   ", ":memory:"]:
                with self.subTest(path=path):
                    with self.assertRaises(ValueError):
                        BackendAPI(path)


class BoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.service = BackendAPI(Path(self.temp.name) / "db.sqlite3")
        self.service.provision_user(user=PROFILE, password=PASSWORD, organization_id="local-org")
        self.client = TestClient(create_app(self.service, allowed_origins=[ORIGIN]), base_url="https://local-api.test")
        self.addCleanup(self.client.close)
        session = self.client.post("/api/v1/auth/login", json={"email": PROFILE["email"], "password": PASSWORD}, headers={"Origin": ORIGIN}).json()["data"]
        self.headers = {"Origin": ORIGIN, "X-CSRF-Token": session["csrfToken"]}
        self.property = {"name": "Local House", "address": "1 Test Road", "city": "Raleigh", "state": "NC", "units": 1}

    def post(self, path, **kwargs):
        return self.client.post("/api/v1"+path, headers=self.headers, **kwargs)

    def test_property_integer_types_and_inclusive_limits(self):
        for units in [True, False, None, "2", 2.5, 2.0, 0, -1, 10001]:
            with self.subTest(units=units):
                self.assertEqual(self.post("/properties", json={**self.property, "units": units}).status_code, 422)
        for units in [1, 10000]:
            response = self.post("/properties", json={**self.property, "units": units})
            self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(len(self.service.get_workspace(user=PROFILE)["properties"]), 2)

    def test_blank_chat_text_and_scope_are_rejected_before_stub(self):
        base = {"question": "Evidence?", "scope": {"type": "lease", "id": "lease-1"}, "asOf": "2026-11-01"}
        for update in [{"question": " \n\t"}, {"question": "x"*2001}, {"scope": {"type": "lease", "id": "   "}}, {"question": None}, {"scope": []}, {"asOf": "2026-02-30"}]:
            with self.subTest(update=update):
                self.assertEqual(self.post("/assistant/messages", json={**base, **update}).status_code, 422)

    def test_duplicate_json_fields_do_not_commit(self):
        raw = b'{"name":"House","address":"1 Road","city":"Raleigh","state":"NC","units":1,"units":2}'
        response = self.client.post("/api/v1/properties", content=raw, headers={**self.headers, "Content-Type": "application/json"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.service.get_workspace(user=PROFILE)["properties"], [])

    def test_import_rejects_unsafe_cents_and_invalid_due_or_notice_days(self):
        property = self.service.create_property(user=PROFILE, **self.property)
        tenant = {"id": "tenant", "name": "Maya Chen", "email": "tenant@example.test", "role": "tenant", "permissions": ["lease:read"]}
        self.service.provision_user(user=tenant, password=PASSWORD, organization_id="local-org")
        root = Path(__file__).resolve().parents[1]
        lease = json.loads((root / "contracts/examples.json").read_text(encoding="utf-8"))["workspace"]["data"]["leases"][0]
        lease.update(propertyId=property["id"], tenantId="tenant", tenantName=tenant["name"])
        for fields in [{"rent": 2**53+1}, {"deposit": 2**53+1}, {"dueDay": 0}, {"dueDay": 32}, {"noticeDays": -1}]:
            with self.subTest(fields=fields):
                with self.assertRaises(APIError) as error:
                    self.service.import_lease(organization_id="local-org", lease={**lease, **fields}, clauses=[])
                self.assertEqual(error.exception.status, 422)
        self.assertEqual(self.service.get_workspace(user=PROFILE)["leases"], [])


    def test_extreme_unicode_and_control_text_never_commit(self):
        for text in ["bad\ud800", "bad\u0000text", "bad\u0001text"]:
            with self.subTest(text=repr(text)):
                raw = json.dumps({**self.property, "name": text}).encode("ascii")
                response = self.client.post("/api/v1/properties", content=raw, headers={**self.headers, "Content-Type": "application/json"})
                self.assertEqual(response.status_code, 422)
        self.assertEqual(self.service.get_workspace(user=PROFILE)["properties"], [])
        good = self.post("/properties", json={**self.property, "name": "House \u00e9 \U0001f3e0"})
        self.assertEqual(good.status_code, 200, good.text)

    def test_extreme_json_depth_nonfinite_and_size(self):
        bodies = [(b"["*70+b"0"+b"]"*70, 400), (b"["*1500+b"0"+b"]"*1500, 400),
                  (b'{"name":"House","address":"Road","city":"Raleigh","state":"NC","units":NaN}', 400),
                  (b'{"name":"House","address":"Road","city":"Raleigh","state":"NC","units":Infinity}', 400),
                  (b'{"name":"'+b"a"*65536+b'"}', 413)]
        for raw, status in bodies:
            response = self.client.post("/api/v1/properties", content=raw, headers={**self.headers, "Content-Type": "application/json"})
            self.assertEqual(response.status_code, status, response.text[:100])
        self.assertEqual(self.service.get_workspace(user=PROFILE)["properties"], [])

    def test_extreme_multipart_integer_is_a_validation_error(self):
        tomorrow = (date.fromisoformat(self.service._today())+timedelta(days=1)).isoformat()
        for version in ["9"*5000, str(2**53), "1.0", "true"]:
            response = self.post("/policies", data={"state": "NC", "familyId": "missing", "expectedVersion": version, "effectiveFrom": tomorrow}, files={"file": ("policy.pdf", b"%PDF-1.7 fixture", "application/pdf")})
            self.assertEqual(response.status_code, 422, response.text[:100])
        self.assertEqual(self.service.get_workspace(user=PROFILE)["policies"], [])

    def test_exact_pdf_limit_is_accepted_and_ready_revision_cannot_be_canceled(self):
        tomorrow = (date.fromisoformat(self.service._today())+timedelta(days=1)).isoformat()
        content = b"%PDF-1.7\n"+b"x"*(10*1024*1024-9)
        self.assertEqual(len(content), 10*1024*1024)
        response = self.post("/policies", data={"state": "NC", "title": "Limit", "category": "other", "effectiveFrom": tomorrow}, files={"file": ("limit.pdf", content, "application/pdf")})
        self.assertEqual(response.status_code, 200, response.text[:100])
        policy = response.json()["data"]
        # Simulate the trusted worker completing a revision; update both representations.
        with closing(sqlite3.connect(self.service.database)) as db, db:
            policy["status"] = "ready"
            db.execute("UPDATE policies SET status='ready', payload=? WHERE id=?", (json.dumps(policy), policy["id"]))
        response = self.client.delete("/api/v1/policies/"+policy["id"], headers=self.headers)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(len(self.service.get_workspace(user=PROFILE)["policies"]), 1)


if __name__ == "__main__":
    unittest.main()

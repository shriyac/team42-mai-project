"""Automatic first-run initialization and preservation tests."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import hashlib
import io
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from fastapi.testclient import TestClient
from pypdf import PdfReader
from laga.api import create_app
from laga.backend_api import BackendAPI
from laga.bootstrap import ROOT, bootstrap_database, policy_pdf


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.service = BackendAPI(Path(self.temp.name) / "data/backend.sqlite3")
        self.credentials = Path(self.temp.name) / "data/backend-bootstrap-login.json"

    def test_deployment_password_is_first_bootstrap_only(self):
        password = "deployment-test-password-123456789"
        with patch.dict(os.environ, {"LAGA_BOOTSTRAP_PASSWORD": password}):
            bootstrap_database(self.service)
        with patch.dict(os.environ, {"LAGA_BOOTSTRAP_PASSWORD": "another-deployment-password-123456789"}):
            bootstrap_database(self.service)
        account = json.loads(self.credentials.read_text(encoding="utf-8"))["accounts"][0]
        session, _ = self.service.post_auth_login(email=account["email"], password=password, session_token=None, client_key="deployment-test")
        self.assertEqual(session["user"]["email"], account["email"])

    def test_short_deployment_password_leaves_no_accounts(self):
        with patch.dict(os.environ, {"LAGA_BOOTSTRAP_PASSWORD": "short"}):
            with self.assertRaises(ValueError):
                bootstrap_database(self.service)
        with closing(sqlite3.connect(self.service.database)) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM users").fetchone()[0], 0)

    def test_all_bootstrap_accounts_authenticate_with_the_installation_password(self):
        bootstrap_database(self.service)
        credentials = json.loads(self.credentials.read_text(encoding="utf-8"))
        self.assertEqual(len(credentials["accounts"]), 11)
        for account in credentials["accounts"]:
            with self.subTest(email=account["email"]):
                session, _ = self.service.post_auth_login(
                    email=account["email"], password=credentials["password"],
                    session_token=None, client_key=account["email"])
                self.assertEqual(session["user"]["email"], account["email"])
                self.assertEqual(session["user"]["role"], account["role"])
                workspace = self.service.get_workspace(user=session["user"])
                if account["role"] == "tenant":
                    self.assertEqual(len(workspace["leases"]), 1)
                    self.assertEqual(workspace["leases"][0]["tenantId"], session["user"]["id"])

    def test_fresh_bootstrap_has_real_docs_logins_scoped_workspaces_and_safe_summary(self):
        result = bootstrap_database(self.service)
        self.assertEqual(result["status"], "bootstrapped")
        self.assertEqual([result[k] for k in ["users", "properties", "leases", "leaseDocuments", "policies", "requests"]], [11, 3, 10, 10, 9, 4])
        login = json.loads(self.credentials.read_text(encoding="utf-8"))
        self.assertNotIn(login["password"], json.dumps(result))
        self.assertNotIn(login["password"].encode(), Path(self.service.database).read_bytes())
        session, _ = self.service.post_auth_login(email="alex@alderliving.example", password=login["password"], session_token=None, client_key="landlord")
        workspace = self.service.get_workspace(user=session["user"])
        self.assertTrue(workspace["demo"])
        self.assertEqual(workspace["summary"]["occupied"], 10)
        self.assertEqual(workspace["summary"]["units"], 12)
        tenant_session, _ = self.service.post_auth_login(email="maya@example.test", password=login["password"], session_token=None, client_key="tenant")
        tenant = self.service.get_workspace(user=tenant_session["user"])
        self.assertEqual([l["id"] for l in tenant["leases"]], ["lease-1"])
        self.assertEqual([p["id"] for p in tenant["properties"]], ["property-1"])
        self.assertEqual(len(self.service.get_leases_id(user=tenant_session["user"], id="lease-1")["clauses"]), 4)
        with closing(sqlite3.connect(self.service.database)) as db:
            for doc_id, file, digest in db.execute("SELECT id,file,content_hash FROM lease_documents"):
                self.assertEqual(hashlib.sha256(file).hexdigest(), digest)
                self.assertEqual(len(PdfReader(io.BytesIO(file)).pages), 12, doc_id)
            for payload, file in db.execute("SELECT payload,file FROM policies"):
                policy = json.loads(payload)
                pdf = PdfReader(io.BytesIO(file), strict=True)
                self.assertEqual(len(pdf.pages), 1)
                text = pdf.pages[0].extract_text()
                self.assertIn(policy["id"], text)
                self.assertIn("SYNTHETIC POLICY", text)
                self.assertEqual(policy["contentHash"], hashlib.sha256(file).hexdigest())
                self.assertEqual(policy["status"], "uploaded")
                self.assertEqual(policy["compliance"]["status"], "pending")
                self.assertIsNone(policy["excerpt"])

    def test_installations_generate_distinct_passwords(self):
        # Test generation deterministically, never comparing inherited secrets.
        with patch.dict(os.environ):
            os.environ.pop("LAGA_BOOTSTRAP_PASSWORD", None)
            with patch("laga.bootstrap.secrets.token_urlsafe",
                       side_effect=["fictional-generated-password-0001", "fictional-generated-password-0002"]):
                bootstrap_database(self.service)
                other = BackendAPI(Path(self.temp.name) / "developer-b/backend.sqlite3")
                result = bootstrap_database(other)
        first = json.loads(self.credentials.read_text(encoding="utf-8"))
        second = json.loads((Path(other.database).parent / result["credentialsPath"]).read_text(encoding="utf-8"))
        self.assertTrue(first["password"] != second["password"], "Generated test passwords must differ")
        self.assertEqual(first["accounts"], second["accounts"])

    def test_failure_after_credential_creation_removes_file_and_rows(self):
        with closing(sqlite3.connect(self.service.database)) as db, db:
            db.execute("CREATE TRIGGER reject_marker BEFORE INSERT ON bootstrap_runs BEGIN SELECT RAISE(ABORT, 'injected failure'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            bootstrap_database(self.service)
        self.assertFalse(self.credentials.exists())
        with closing(sqlite3.connect(self.service.database)) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM users").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM policies").fetchone()[0], 0)

    def test_repeat_startup_preserves_edits_and_password(self):
        bootstrap_database(self.service)
        original = self.credentials.read_bytes()
        with closing(sqlite3.connect(self.service.database)) as db, db:
            property = json.loads(db.execute("SELECT payload FROM properties WHERE id='property-1'").fetchone()[0])
            property["name"] = "Developer edit"
            db.execute("UPDATE properties SET payload=? WHERE id='property-1'", (json.dumps(property),))
        repeated = bootstrap_database(BackendAPI(self.service.database))
        self.assertEqual(repeated["status"], "already_bootstrapped")
        self.assertEqual(self.credentials.read_bytes(), original)
        with closing(sqlite3.connect(self.service.database)) as db:
            self.assertEqual(json.loads(db.execute("SELECT payload FROM properties WHERE id='property-1'").fetchone()[0])["name"], "Developer edit")
            self.assertEqual(db.execute("SELECT COUNT(*) FROM users").fetchone()[0], 11)

    def test_concurrent_bootstrap_runs_once(self):
        with ThreadPoolExecutor(max_workers=3) as pool:
            results = list(pool.map(lambda _: bootstrap_database(self.service), range(3)))
        self.assertEqual(sorted(r["status"] for r in results), ["already_bootstrapped", "already_bootstrapped", "bootstrapped"])
        self.assertTrue(self.credentials.is_file())

    def test_existing_account_is_not_overwritten_or_mixed_with_fixtures(self):
        user = {"id": "existing", "name": "Existing", "email": "existing@example.test", "role": "landlord", "permissions": []}
        self.service.provision_user(user=user, password="existing-password-123", organization_id="existing-org")
        self.assertEqual(bootstrap_database(self.service, fixture_path="missing.json")["status"], "existing_database")
        self.assertFalse(self.credentials.exists())
        with closing(sqlite3.connect(self.service.database)) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM users").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM policies").fetchone()[0], 0)

    def test_mid_transaction_failure_rolls_back_and_retry_succeeds(self):
        with closing(sqlite3.connect(self.service.database)) as db, db:
            db.execute("CREATE TRIGGER reject_seed BEFORE INSERT ON policies BEGIN SELECT RAISE(ABORT, 'injected failure'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            bootstrap_database(self.service)
        self.assertFalse(self.credentials.exists())
        with closing(sqlite3.connect(self.service.database)) as db, db:
            for table in ["users", "leases", "properties", "lease_documents", "policies", "bootstrap_runs"]:
                self.assertEqual(db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], 0)
            db.execute("DROP TRIGGER reject_seed")
        self.assertEqual(bootstrap_database(self.service)["status"], "bootstrapped")

    def test_corrupt_snapshot_is_not_partially_seeded(self):
        fixture = json.loads((ROOT / "contracts/bootstrap.json").read_text(encoding="utf-8"))
        fixture["policies"][0]["propertyId"] = "foreign"
        broken = Path(self.temp.name) / "broken.json"
        broken.write_text(json.dumps(fixture), encoding="utf-8")
        with self.assertRaises(ValueError):
            bootstrap_database(self.service, fixture_path=broken)
        with closing(sqlite3.connect(self.service.database)) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM users").fetchone()[0], 0)
        self.assertFalse(self.credentials.exists())

    def test_application_default_bootstraps_and_can_be_disabled(self):
        with patch.dict("os.environ", {"LAGA_DATABASE": self.service.database, "LAGA_BOOTSTRAP": "1"}):
            app = create_app(secure_cookies=False, allowed_origins=["http://localhost:5174"])
        self.assertEqual(app.state.bootstrap["status"], "bootstrapped")
        login = json.loads(self.credentials.read_text(encoding="utf-8"))
        with TestClient(app, base_url="http://localhost") as client:
            response = client.post("/api/v1/auth/login", json={"email": "alex@alderliving.example", "password": login["password"]}, headers={"Origin": "http://localhost:5174"})
            self.assertEqual(response.status_code, 200, response.text)
            workspace = client.get("/api/v1/workspace")
            self.assertEqual(workspace.status_code, 200)
            self.assertEqual(len(workspace.json()["data"]["leases"]), 10)
        other = Path(self.temp.name) / "empty.sqlite3"
        with patch.dict("os.environ", {"LAGA_DATABASE": str(other), "LAGA_BOOTSTRAP": "0"}):
            empty = create_app()
        self.assertEqual(empty.state.bootstrap["status"], "disabled")
        with closing(sqlite3.connect(other)) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM users").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()

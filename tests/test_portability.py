"""Paths must survive cwd changes and copied installations without resetting data."""
from contextlib import closing
import json
import os
from pathlib import Path, PureWindowsPath
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from fastapi.testclient import TestClient
from laga.api import create_app, default_origins
from laga.backend_api import BackendAPI, DEFAULT_DATABASE
from laga.bootstrap import bootstrap_database
from laga.paths import PROJECT_ROOT


class PortabilityTests(unittest.TestCase):
    def test_root_relative_defaults_ignore_working_directory(self):
        self.assertFalse(DEFAULT_DATABASE.is_absolute())
        with tempfile.TemporaryDirectory() as directory:
            code = "from laga.paths import resolve_project_path; from laga.api import load_contract; print(load_contract()['info']['version']); print(resolve_project_path('data/backend.sqlite3'))"
            result = subprocess.run([sys.executable, "-c", code], cwd=directory, env={**os.environ, "PYTHONPATH": str(PROJECT_ROOT / "src"), "LAGA_CONTRACT_PATH": "contracts/openapi.json"}, capture_output=True, text=True, check=True)
        self.assertEqual(result.stdout.splitlines()[0], "1.1.0")
        self.assertEqual(Path(result.stdout.splitlines()[1]), PROJECT_ROOT / "data/backend.sqlite3")

    def test_added_user_does_not_change_credential_migration_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            service = BackendAPI(Path(directory) / "backend.sqlite3")
            bootstrap_database(service)
            profile = {"id":"000-added-account", "name":"Added Account", "email":"added@example.test", "role":"tenant", "permissions":["lease:read"]}
            service.provision_user(user=profile, password="added-user-password", organization_id="org-alder-demo")
            self.assertEqual(bootstrap_database(service)["status"], "already_bootstrapped")
            session,_ = service.post_auth_login(email=profile["email"], password="added-user-password", session_token=None, client_key="added-user")
            self.assertEqual(session["user"]["id"], profile["id"])

    def test_legacy_absolute_metadata_migrates_without_resetting_state(self):
        with tempfile.TemporaryDirectory() as directory:
            service = BackendAPI(Path(directory) / "data/backend.sqlite3")
            bootstrap_database(service)
            credentials = Path(directory) / "data/backend-bootstrap-login.json"
            original = json.loads(credentials.read_text(encoding="utf-8"))
            old_root = PureWindowsPath(chr(90)+":"+chr(92), "previous-workstation", "Laga", "data")
            original["database"] = str(old_root / "backend.sqlite3")
            original.pop("pathBase", None)
            credentials.write_text(json.dumps(original), encoding="utf-8")
            with closing(sqlite3.connect(service.database)) as db, db:
                users_before = db.execute("SELECT id,password_hash FROM users ORDER BY id").fetchall()
                db.execute("UPDATE bootstrap_runs SET credentials_path=?", (str(old_root / credentials.name),))
            result = bootstrap_database(service)
            updated = json.loads(credentials.read_text(encoding="utf-8"))
            self.assertEqual(updated["password"], original["password"])
            self.assertEqual(updated["accounts"], original["accounts"])
            self.assertEqual(updated["database"], "backend.sqlite3")
            self.assertEqual(updated["pathBase"], "credentialsDirectory")
            self.assertEqual(result["credentialsPath"], credentials.name)
            with closing(sqlite3.connect(service.database)) as db:
                self.assertEqual(db.execute("SELECT id,password_hash FROM users ORDER BY id").fetchall(), users_before)
                self.assertEqual(db.execute("SELECT credentials_path FROM bootstrap_runs").fetchone()[0], credentials.name)
            session, _ = service.post_auth_login(email="alex@alderliving.example", password=updated["password"], session_token=None, client_key="relocation")
            self.assertEqual(len(service.get_workspace(user=session["user"])["leases"]), 10)

    def test_copied_laga_runs_after_original_folder_becomes_unavailable(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            first = base / "first workstation" / "Laga"
            for name in ["src/laga", "contracts", "docs/synthetic-leases", "scripts", "frontend/src"]:
                shutil.copytree(PROJECT_ROOT / name, first / name, ignore=shutil.ignore_patterns("__pycache__"))
            shutil.copy2(PROJECT_ROOT / "package.json", first / "package.json")
            elsewhere = base / "unrelated cwd"
            elsewhere.mkdir()
            code = r"""
import json
from laga.api import create_app
from laga.paths import PROJECT_ROOT
app=create_app()
credentials=json.loads((PROJECT_ROOT/'data/backend-bootstrap-login.json').read_text())
session,_=app.state.backend.post_auth_login(email='alex@alderliving.example',password=credentials['password'],session_token=None,client_key='copied-installation')
assert len(app.state.backend.get_workspace(user=session['user'])['leases'])==10
assert credentials['database']=='data/backend.sqlite3'
assert credentials['pathBase']=='Laga'
assert app.state.bootstrap['credentialsPath']=='data/backend-bootstrap-login.json'
print(json.dumps({'status':app.state.bootstrap['status'],'password':credentials['password']}))
"""
            def run(root):
                env={**os.environ, "PYTHONPATH": str(root / "src"), "LAGA_BOOTSTRAP": "1"}
                for key in ["LAGA_DATABASE", "LAGA_CONTRACT_PATH"]:
                    env.pop(key, None)
                result=subprocess.run([sys.executable,"-c",code],cwd=elsewhere,env=env,capture_output=True,text=True,check=True)
                return json.loads(result.stdout)
            before=run(first)
            moved=base / "replit-style workspace" / "Laga"
            shutil.copytree(first,moved)
            first.rename(first.with_name("original unavailable"))
            after=run(moved)
            self.assertEqual(before["status"],"bootstrapped")
            self.assertEqual(after["status"],"already_bootstrapped")
            self.assertEqual(before["password"],after["password"])
            for script in ["export-bootstrap-fixtures.mjs", "export-contract-examples.mjs"]:
                subprocess.run(["node",str(moved / "scripts" / script)],cwd=elsewhere,capture_output=True,text=True,check=True)
            self.assertFalse((elsewhere / "contracts").exists())

    def test_replit_preview_https_origin_can_sign_in(self):
        with tempfile.TemporaryDirectory() as directory:
            service = BackendAPI(Path(directory) / "db.sqlite3")
            profile = json.loads((PROJECT_ROOT / "contracts/bootstrap.json").read_text(encoding="utf-8"))["users"][0]
            service.provision_user(user=profile, password="preview-test-password", organization_id="preview-org")
            with patch.dict(os.environ, {"PORT":"5000", "REPLIT_DEV_DOMAIN":"portable-preview.replit.dev"}):
                previous = os.environ.pop("LAGA_ALLOWED_ORIGINS", None)
                try:
                    app = create_app(service)
                    with TestClient(app, base_url="https://api.test") as client:
                        response = client.post("/api/v1/auth/login", json={"email":profile["email"], "password":"preview-test-password"}, headers={"Origin":"https://portable-preview.replit.dev"})
                        self.assertEqual(response.status_code, 200, response.text)
                        self.assertEqual(client.get("/api/v1/workspace").status_code, 200)
                finally:
                    if previous is not None: os.environ["LAGA_ALLOWED_ORIGINS"] = previous

    def test_replit_preview_origin_and_port_come_from_environment(self):
        with patch.dict(os.environ, {"PORT":"5000", "REPLIT_DEV_DOMAIN":"portable-preview.replit.dev"}):
            previous = os.environ.pop("LAGA_ALLOWED_ORIGINS", None)
            previous_port = os.environ.pop("LAGA_LOCAL_UI_PORT", None)
            try:
                self.assertIn("https://portable-preview.replit.dev", default_origins())
                self.assertIn("http://localhost:5000", default_origins())
            finally:
                if previous is not None: os.environ["LAGA_ALLOWED_ORIGINS"] = previous
                if previous_port is not None: os.environ["LAGA_LOCAL_UI_PORT"] = previous_port


if __name__ == "__main__":
    unittest.main()

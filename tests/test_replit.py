"""Production launcher and published-origin regressions."""
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import tomllib
import unittest
from unittest.mock import patch
from laga.api import default_origins

ROOT = Path(__file__).resolve().parents[1]

class ReplitTests(unittest.TestCase):
    def test_publishing_uses_explicit_project_local_dependency_install(self):
        config = tomllib.loads((ROOT/".replit").read_text())
        self.assertIs(config["packager"]["features"]["enabledForHosting"], False)
        command = " ".join(config["deployment"]["build"])
        self.assertIn("npm ci --include=dev", command)
        self.assertIn('python -m pip install --target .pythonlibs/lib/python3.11/site-packages', command)
        self.assertIn('.[api]', command)
        self.assertIn("npm run build", command)
        project = tomllib.loads((ROOT/"pyproject.toml").read_text())
        self.assertIs(project["tool"]["uv"]["package"], False)

    def test_published_domains_and_explicit_override(self):
        with patch.dict(os.environ, {"REPLIT_DOMAINS":"demo.replit.app,custom.example", "REPLIT_DEV_DOMAIN":"preview.replit.dev", "LAGA_ALLOWED_ORIGINS":"https://explicit.example"}):
            self.assertEqual(default_origins(), ["https://explicit.example"])
            del os.environ["LAGA_ALLOWED_ORIGINS"]
            origins = default_origins()
            for host in ["demo.replit.app", "custom.example", "preview.replit.dev"]:
                self.assertIn("https://"+host, origins)
            os.environ["REPLIT_DOMAINS"] = "bad.example/path"
            with self.assertRaises(ValueError):
                default_origins()

    def test_production_process_bootstraps_and_serves_ui_and_api(self):
        with tempfile.TemporaryDirectory() as directory:
            ports = []
            for _ in range(2):
                with socket.socket() as listener:
                    listener.bind(("127.0.0.1", 0))
                    ports.append(listener.getsockname()[1])
            env = {**os.environ, "PORT":str(ports[0]), "LAGA_LOCAL_API_PORT":str(ports[1]),
                   "LAGA_DATABASE":str(Path(directory)/"backend.sqlite3"),
                   "LAGA_PYTHON":os.sys.executable, "REPLIT_DOMAINS":"demo.replit.app", "LAGA_ALLOWED_ORIGINS":"https://demo.replit.app", "LAGA_BOOTSTRAP_PASSWORD":"isolated-replit-test-password-123456789"}
            result = subprocess.run(["node", str(ROOT/"scripts/start-app.mjs"), "--check"], cwd=directory, env=env, capture_output=True, text=True, timeout=45)
            self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
            self.assertIn("Production frontend and Python API startup check passed", result.stdout)
            self.assertTrue((Path(directory)/"backend-bootstrap-login.json").is_file())

    def test_preview_https_bootstrap_login_proxy_and_shutdown(self):
        with tempfile.TemporaryDirectory() as directory:
            with socket.socket() as first, socket.socket() as second:
                first.bind(("127.0.0.1", 0)); second.bind(("127.0.0.1", 0))
                ui_port, api_port = first.getsockname()[1], second.getsockname()[1]
            env = {**os.environ, "PORT":str(ui_port), "LAGA_LOCAL_UI_PORT":str(ui_port), "LAGA_LOCAL_API_PORT":str(api_port),
                   "LAGA_DATABASE":str(Path(directory)/"backend.sqlite3"), "LAGA_PYTHON":os.sys.executable,
                   "REPLIT_DEV_DOMAIN":"preview.replit.dev", "LAGA_ALLOWED_ORIGINS":"https://preview.replit.dev",
                   "LAGA_BOOTSTRAP_PASSWORD":"isolated-preview-test-password-123456789"}
            result = subprocess.run(["node", str(ROOT/"scripts/dev-local.mjs"), "--check"], cwd=directory, env=env, capture_output=True, text=True, timeout=45)
            self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
            self.assertIn("Local API and UI startup check passed", result.stdout)

    def test_launchers_fail_fast_on_bad_ports_or_missing_python(self):
        for script in ["dev-local.mjs", "start-app.mjs"]:
            for ui, api in [("5000", "5000"), ("bad", "8001"), ("5000", "8e3"), ("0", "8001")]:
                with self.subTest(script=script, ui=ui, api=api):
                    env = {**os.environ, "PORT":ui, "LAGA_LOCAL_UI_PORT":ui, "LAGA_LOCAL_API_PORT":api}
                    result = subprocess.run(["node", str(ROOT/"scripts"/script), "--check"], env=env, capture_output=True, text=True, timeout=10)
                    self.assertNotEqual(result.returncode, 0)
            env = {**os.environ, "PORT":"5198", "LAGA_LOCAL_UI_PORT":"5198", "LAGA_LOCAL_API_PORT":"8198", "LAGA_PYTHON":"nonexistent-laga-python-command"}
            result = subprocess.run(["node", str(ROOT/"scripts"/script), "--check"], env=env, capture_output=True, text=True, timeout=10)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("ENOENT", result.stderr)

    def test_production_public_port_conflict_stops_with_failure(self):
        with tempfile.TemporaryDirectory() as directory, socket.socket() as public, socket.socket() as internal:
            public.bind(("0.0.0.0", 0)); public.listen()
            internal.bind(("127.0.0.1", 0)); api_port = internal.getsockname()[1]; internal.close()
            env = {**os.environ, "PORT":str(public.getsockname()[1]), "LAGA_LOCAL_API_PORT":str(api_port),
                   "LAGA_DATABASE":str(Path(directory)/"backend.sqlite3"), "LAGA_PYTHON":os.sys.executable}
            result = subprocess.run(["node", str(ROOT/"scripts/start-app.mjs"), "--check"], env=env, capture_output=True, text=True, timeout=20)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("EADDRINUSE", result.stderr)

    def test_production_missing_build_fails_before_creating_database(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder/"scripts").mkdir()
            for filename in ["serve.mjs", "start-app.mjs"]:
                (folder/"scripts"/filename).write_bytes((ROOT/"scripts"/filename).read_bytes())
            result = subprocess.run(["node", str(folder/"scripts/start-app.mjs"), "--check"], env={**os.environ,"PORT":"5197","LAGA_LOCAL_API_PORT":"8197"}, capture_output=True, text=True, timeout=10)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Frontend build is missing", result.stderr)
            self.assertFalse((folder/"data").exists())

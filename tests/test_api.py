"""Endpoint/security/signature tests against the UI's canonical contract."""
from contextlib import closing
import inspect
import copy
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import os
import socket
import subprocess
import threading
import time
import uvicorn
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from fastapi.testclient import TestClient
from laga.api import COOKIE, MAX_PDF, check_signatures, create_app, load_contract, validate
from laga.backend_api import APIError, BackendAPI

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = json.loads((ROOT / "contracts/integration-examples.json").read_text())
PROFILE = json.loads((ROOT / "contracts/examples.json").read_text())["session"]["data"]["user"]
PASSWORD = "integration-password-123"
ORIGIN = "https://ui.test"


class APITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.clock = [datetime(2026, 11, 1, 17, tzinfo=timezone.utc).timestamp()]
        self.database = Path(self.temp.name) / "api.sqlite3"
        self.service = BackendAPI(self.database, session_seconds=60, now=lambda: self.clock[0])
        self.service.provision_user(user=PROFILE, password=PASSWORD, organization_id="org-test")
        self.client = TestClient(create_app(self.service, allowed_origins=[ORIGIN]), base_url="https://api.test")
        self.addCleanup(self.client.close)

    def login(self, email=PROFILE["email"], password=PASSWORD):
        response = self.client.post("/api/v1/auth/login", json={"email": email, "password": password}, headers={"Origin": ORIGIN})
        self.assertEqual(response.status_code, 200, response.text)
        self.csrf = response.json()["data"]["csrfToken"]
        return response

    def mutation(self, method, path, **kwargs):
        return self.client.request(method, "/api/v1"+path, headers={"Origin": ORIGIN, "X-CSRF-Token": self.csrf}, **kwargs)

    def test_every_backend_method_documents_purpose_inputs_outputs_and_exceptions(self):
        for name, method in inspect.getmembers(BackendAPI, inspect.isfunction):
            doc = inspect.getdoc(method) or ""
            for label in ["Purpose:", "Inputs:", "Outputs:", "Raises:"]:
                self.assertIn(label, doc, name)

    def test_contract_signatures_and_route_inventory(self):
        contract = load_contract()
        check_signatures(contract, self.service)
        actual = {(m.lower(), r.path.removeprefix("/api/v1"), r.operation_id)
                  for r in self.client.app.routes for m in r.methods}
        expected = {(m, p, o["operationId"]) for p, methods in contract["paths"].items() for m, o in methods.items()}
        self.assertEqual(actual, expected)
        changed = copy.deepcopy(contract)
        changed["components"]["schemas"]["AskInput"]["properties"]["newField"] = {"type": "string"}
        with self.assertRaises(ValueError):
            check_signatures(changed, self.service)

    def test_anonymous_login_cookie_reload_logout_and_replay(self):
        anonymous = self.client.get("/api/v1/auth/session")
        self.assertEqual(anonymous.json(), {"data": {"user": None, "csrfToken": None}})
        self.assertEqual(self.client.get("/api/v1/workspace").status_code, 401)
        response = self.login()
        cookie = response.headers["set-cookie"]
        for attribute in ["HttpOnly", "Secure", "SameSite=lax", "Path=/api/v1"]:
            self.assertIn(attribute, cookie)
        token = self.client.cookies.get(COOKIE)
        self.assertEqual(self.client.get("/api/v1/auth/session").json()["data"], response.json()["data"])
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertNotIn(PASSWORD.encode(), self.database.read_bytes())
        self.assertNotIn(token.encode(), self.database.read_bytes())
        logout = self.mutation("POST", "/auth/logout", json={})
        self.assertEqual(logout.json(), {"data": {"signedOut": True}})
        self.client.cookies.set(COOKIE, token)
        self.assertIsNone(self.client.get("/api/v1/auth/session").json()["data"]["user"])

    def test_session_rotation_expiry_and_persistence(self):
        self.login()
        old_token, old_csrf = self.client.cookies.get(COOKIE), self.csrf
        self.login()
        new_token = self.client.cookies.get(COOKIE)
        self.assertNotEqual(new_token, old_token)
        self.assertNotEqual(self.csrf, old_csrf)
        restarted = BackendAPI(self.database, now=lambda: self.clock[0])
        self.assertIsNone(restarted.get_auth_session(session_token=old_token)["user"])
        self.assertEqual(restarted.get_auth_session(session_token=new_token)["user"]["id"], PROFILE["id"])
        self.clock[0] += 60
        self.assertIsNone(self.client.get("/api/v1/auth/session").json()["data"]["user"])
        self.assertEqual(self.client.get("/api/v1/workspace").status_code, 401)

    def test_login_and_mutation_origin_csrf_protection(self):
        for origin in [None, "null", "https://evil.test"]:
            headers = {"Origin": origin} if origin else {}
            self.assertEqual(self.client.post("/api/v1/auth/login", json=EXAMPLES["login"], headers=headers).status_code, 403)
        self.login()
        for headers in [{"Origin": ORIGIN}, {"Origin": ORIGIN, "X-CSRF-Token": "wrong"}, {"Origin": "https://evil.test", "X-CSRF-Token": self.csrf}]:
            self.assertEqual(self.client.post("/api/v1/auth/logout", json={}, headers=headers).status_code, 403)
        self.assertIsNotNone(self.client.get("/api/v1/auth/session").json()["data"]["user"])

    def test_invalid_credentials_generic_rate_limited_and_no_role_injection(self):
        for email in [PROFILE["email"], "unknown@example.test"]:
            r = self.client.post("/api/v1/auth/login", json={"email": email, "password": "wrong"}, headers={"Origin": ORIGIN})
            self.assertEqual(r.status_code, 401)
            self.assertEqual(r.json()["error"]["message"], "Email or password is incorrect.")
        r = self.client.post("/api/v1/auth/login", json={"email": PROFILE["email"], "password": PASSWORD, "role": "landlord"}, headers={"Origin": ORIGIN})
        self.assertEqual(r.status_code, 422)
        for _ in range(8):
            self.client.post("/api/v1/auth/login", json={"email": "unknown@example.test", "password": "wrong"}, headers={"Origin": ORIGIN})
        r = self.client.post("/api/v1/auth/login", json={"email": PROFILE["email"], "password": PASSWORD}, headers={"Origin": ORIGIN})
        self.assertEqual(r.status_code, 429)
        self.clock[0] += 901
        self.login()

    def test_business_routes_persist_or_fail_with_expected_status(self):
        self.login()
        for path, status in [("/workspace", 200), ("/leases/lease-1", 404)]:
            r = self.client.get("/api/v1"+path)
            self.assertEqual(r.status_code, status, r.text)
        cases = [("POST", "/properties", EXAMPLES["propertyRegistration"]),
                 ("POST", "/assistant/messages", EXAMPLES["ask"]),
                 ("POST", "/requests/request-1/reply", EXAMPLES["landlordReply"]),
                 ("DELETE", "/policies/policy-1", None)]
        for (method, path, body), status in zip(cases, [200, 503, 404, 404]):
            r = self.mutation(method, path, **({"json": body} if body else {}))
            self.assertEqual(r.status_code, status, r.text)
            if status != 200:
                validate(load_contract(), {"$ref": "#/components/schemas/Error"}, r.json())
        tenant = {"id": "tenant-1", "name": "Test Tenant", "email": "tenant@example.test", "role": "tenant", "permissions": ["lease:read", "requests:create"]}
        self.service.provision_user(user=tenant, password=PASSWORD, organization_id="org-test")
        self.login(tenant["email"])
        self.assertEqual(self.mutation("POST", "/requests", json=EXAMPLES["clarificationRequest"]).status_code, 404)
        self.assertEqual(self.mutation("POST", "/properties", json=EXAMPLES["propertyRegistration"]).status_code, 403)
        self.assertEqual(self.mutation("POST", "/requests/request-1/reply", json=EXAMPLES["landlordReply"]).status_code, 403)
        ask = {**EXAMPLES["ask"], "scope": {"type": "portfolio", "id": None}}
        self.assertEqual(self.mutation("POST", "/assistant/messages", json=ask).status_code, 403)

    def test_upload_validation_and_new_version_signature(self):
        self.login()
        fields = {k: str(v) for k, v in EXAMPLES["newPolicyMultipart"].items() if k not in {"file", "propertyId"}}
        r = self.mutation("POST", "/policies", data=fields, files={"file": ("policy.pdf", b"%PDF-1.7\\nfixture", "application/pdf")})
        self.assertEqual(r.status_code, 200, r.text)
        first = r.json()["data"]
        version_fields = {"familyId": first["familyId"], "expectedVersion": "1", "state": "NC", "effectiveFrom": "2026-11-03"}
        r = self.mutation("POST", "/policies", data=version_fields, files={"file": ("v2.pdf", b"%PDF-1.7\\nfixture", "application/pdf")})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["data"]["version"], 2)
        for name, data, status in [("p.pdf", b"", 422), ("p.pdf", b"not PDF", 422), ("p.txt", b"%PDF-1.7", 422), ("p.pdf", b"%PDF-"+b"x"*MAX_PDF, 413)]:
            r = self.mutation("POST", "/policies", data=fields, files={"file": (name, data, "application/pdf")})
            self.assertEqual(r.status_code, status, r.text)
        version = {k: str(v) for k, v in EXAMPLES["newVersionMultipart"].items() if k not in {"file", "expectedVersion"}}
        r = self.mutation("POST", "/policies", data=version, files={"file": ("p.pdf", b"%PDF-1.7", "application/pdf")})
        self.assertEqual(r.status_code, 422)

    def test_invalid_json_dates_unknown_fields_and_response_guard(self):
        self.login()
        r = self.mutation("POST", "/assistant/messages", json={**EXAMPLES["ask"], "asOf": "2026-02-30"})
        self.assertEqual(r.status_code, 422)
        r = self.client.post("/api/v1/properties", content=b"{", headers={"Origin": ORIGIN, "X-CSRF-Token": self.csrf, "Content-Type": "application/json"})
        self.assertEqual(r.status_code, 400)
        r = self.mutation("POST", "/properties", json={**EXAMPLES["propertyRegistration"], "ownerId": "foreign"})
        self.assertEqual(r.status_code, 422)
        class BadBackend(BackendAPI):
            def get_workspace(self, *, user):
                return {"private": "bad DTO must not leak"}
        app = create_app(BadBackend(self.database, now=lambda: self.clock[0]), allowed_origins=[ORIGIN])
        with TestClient(app, base_url="https://api.test") as other:
            other.cookies.update(self.client.cookies)
            r = other.get("/api/v1/workspace")
            self.assertEqual(r.status_code, 503)
            self.assertEqual(r.json()["error"]["code"], "BACKEND_CONTRACT_ERROR")
            self.assertNotIn("private", r.text)

    def test_cors_and_unknown_routes_use_envelopes(self):
        r = self.client.options("/api/v1/auth/login", headers={"Origin": ORIGIN, "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "Content-Type,X-CSRF-Token"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.headers["access-control-allow-origin"], ORIGIN)
        self.assertEqual(r.headers["access-control-allow-credentials"], "true")
        denied = self.client.options("/api/v1/auth/login", headers={"Origin": "https://evil.test", "Access-Control-Request-Method": "POST"})
        self.assertNotIn("access-control-allow-origin", denied.headers)
        for method, path in [("GET", "/api/v1/missing"), ("PUT", "/api/v1/auth/session")]:
            r = self.client.request(method, path)
            self.assertIn(r.status_code, [404, 405])
            validate(load_contract(), {"$ref": "#/components/schemas/Error"}, r.json())


    def test_sqlite_workspace_properties_lease_requests_and_isolation(self):
        self.login()
        property = self.mutation("POST", "/properties", json=EXAMPLES["propertyRegistration"]).json()["data"]
        tenant = {"id": "tenant-1", "name": "Maya Chen", "email": "maya@example.test", "role": "tenant", "permissions": ["lease:read", "requests:create"]}
        other_tenant = {**tenant, "id": "tenant-2", "email": "other@example.test", "name": "Other Tenant"}
        for profile in [tenant, other_tenant]:
            self.service.provision_user(user=profile, password=PASSWORD, organization_id="org-test")
        lease = copy.deepcopy(json.loads((ROOT / "contracts/examples.json").read_text())["workspace"]["data"]["leases"][0])
        lease.update(propertyId=property["id"], tenantId=tenant["id"], tenantName=tenant["name"], paymentStatus="due")
        self.service.import_lease(organization_id="org-test", lease=lease, clauses=[])
        workspace = self.client.get("/api/v1/workspace").json()["data"]
        self.assertEqual(workspace["summary"]["occupied"], 1)
        self.assertEqual(workspace["summary"]["monthlyRent"], lease["rent"])
        self.assertEqual(workspace["summary"]["outstandingRent"], lease["rent"])
        self.assertFalse(workspace["demo"])
        self.assertEqual(workspace["timeZone"], "America/New_York")
        self.assertEqual(self.service.get_user_id(session_token=self.client.cookies.get(COOKIE)), PROFILE["id"])
        with self.assertRaises(APIError) as error:
            self.service.get_user_id(session_token=None)
        self.assertEqual(error.exception.status, 401)
        self.login(tenant["email"])
        detail = self.client.get("/api/v1/leases/"+lease["id"])
        self.assertEqual(detail.status_code, 200, detail.text)
        created = self.mutation("POST", "/requests", json={**EXAMPLES["clarificationRequest"], "leaseId": lease["id"]})
        self.assertEqual(created.status_code, 200, created.text)
        request_id = created.json()["data"]["id"]
        self.login(other_tenant["email"])
        self.assertEqual(self.client.get("/api/v1/leases/"+lease["id"]).status_code, 404)
        own = self.client.get("/api/v1/workspace").json()["data"]
        self.assertEqual(own["leases"], [])
        self.assertEqual(own["properties"], [])
        self.assertEqual(own["requests"], [])
        self.login()
        reply = self.mutation("POST", "/requests/"+request_id+"/reply", json={"reply": "Please send a photo."})
        self.assertEqual(reply.json()["data"]["status"], "answered")
        # A second organization cannot see or mutate any of the first organization's objects.
        foreign = {**PROFILE, "id": "landlord-2", "email": "foreign@example.test"}
        self.service.provision_user(user=foreign, password=PASSWORD, organization_id="org-foreign")
        self.login(foreign["email"])
        self.assertEqual(self.client.get("/api/v1/workspace").json()["data"]["properties"], [])
        self.assertEqual(self.client.get("/api/v1/leases/"+lease["id"]).status_code, 404)
        self.assertEqual(self.mutation("POST", "/requests/"+request_id+"/reply", json={"reply": "foreign"}).status_code, 404)
        restarted = BackendAPI(self.database, now=lambda: self.clock[0])
        self.assertEqual(restarted.get_workspace(user=PROFILE)["properties"][0]["id"], property["id"])

    def test_real_frontend_http_gateway_against_running_python_api(self):
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(create_app(self.service, allowed_origins=[ORIGIN], secure_cookies=False), log_level="error", proxy_headers=False))
        worker = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
        worker.start()
        try:
            deadline = time.monotonic()+10
            while not server.started and time.monotonic() < deadline:
                time.sleep(0.02)
            self.assertTrue(server.started)
            code = r"""
import assert from 'node:assert/strict';
import {createHttpGateway} from './frontend/src/services/httpGateway.js';
let cookie='';
const fetcher=async(url, options={})=>{
 const headers=new Headers(options.headers);
 headers.set('Origin','https://ui.test');
 if(cookie)headers.set('Cookie',cookie);
 const response=await fetch(url,{...options,headers});
 const set=response.headers.getSetCookie();
 if(set.length)cookie=set.at(-1).split(';')[0];
 return response;
};
const api=createHttpGateway({base:process.env.LAGA_TEST_BASE,fetcher,stateVerification:false});
assert.equal((await api.getSession()).user,null);
const session=await api.login({email:'alex@alderliving.example',password:'integration-password-123'});
assert.equal(session.user.id,'landlord-1');
assert.equal((await api.getSession()).csrfToken,session.csrfToken);
assert.equal((await api.getWorkspace()).properties.length,0);
const property=await api.createProperty({name:'Gateway House',address:'1 Test Road',city:'Raleigh',state:'NC',units:2});
assert.equal((await api.getWorkspace()).properties[0].id,property.id);
const policy=await api.uploadPolicy({file:new File(['%PDF-1.7 gateway fixture'],'gateway.pdf',{type:'application/pdf'}),title:'Gateway rules',category:'tenant',propertyId:property.id,state:'NC',effectiveFrom:'2026-11-02'});
assert.equal(policy.status,'uploaded');
assert.equal(policy.version,1);
await api.deletePolicy(policy.id);
assert.equal((await api.getWorkspace()).policies.length,0);
await assert.rejects(api.getLease('foreign'),e=>e.code==='NOT_FOUND');
await assert.rejects(api.ask({question:'Evidence?',scope:{type:'portfolio',id:null},asOf:'2026-11-01'}),e=>e.code==='BACKEND_NOT_IMPLEMENTED');
await api.logout();
assert.equal((await api.getSession()).user,null);
console.log('PASS real frontend HTTP gateway against live Python API');
"""
            result = subprocess.run(["node", "--input-type=module"], input=code, text=True, cwd=ROOT,
                                    env={**os.environ, "LAGA_TEST_BASE": f"http://127.0.0.1:{port}/api/v1"},
                                    capture_output=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        finally:
            server.should_exit = True
            worker.join(timeout=10)
            listener.close()
            self.assertFalse(worker.is_alive())

    def test_policy_transactions_cancellation_boundaries_and_private_bytes(self):
        self.login()
        future = "2026-11-02"
        def upload(**extra):
            return self.service.post_policies(user=PROFILE, file=b"%PDF-1.7 private fixture", filename="../../policy.pdf", content_type="application/pdf", state="NC", **extra)
        first = upload(title="House rules", category="tenant", effectiveFrom=future)
        self.assertEqual(first["status"], "uploaded")
        self.assertEqual(first["compliance"], {"status": "pending"})
        self.assertEqual(first["name"], "policy.pdf")
        self.assertNotIn("file", self.service.get_workspace(user=PROFILE)["policies"][0])
        def concurrent_upload(_):
            try:
                return upload(familyId=first["familyId"], expectedVersion=1, effectiveFrom="2026-11-03")
            except APIError as error:
                return error
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(concurrent_upload, range(2)))
        self.assertEqual(sum(isinstance(o, APIError) and o.status == 409 for o in outcomes), 1)
        latest = next(o for o in outcomes if isinstance(o, dict))
        old = next(p for p in self.service.get_workspace(user=PROFILE)["policies"] if p["id"] == first["id"])
        self.assertEqual(old["effectiveTo"], "2026-11-03")
        with self.assertRaises(APIError) as error:
            self.service.delete_policies_id(user=PROFILE, id=first["id"])
        self.assertEqual(error.exception.status, 409)
        self.service.delete_policies_id(user=PROFILE, id=latest["id"])
        restored = self.service.get_workspace(user=PROFILE)["policies"]
        self.assertEqual(len(restored), 1)
        self.assertIsNone(restored[0]["effectiveTo"])
        with closing(sqlite3.connect(self.database)) as db:
            audit = db.execute("SELECT event, file FROM policy_audit WHERE id=?", (latest["id"],)).fetchone()
        self.assertEqual(audit, ("canceled", b"%PDF-1.7 private fixture"))
        self.clock[0] += 86400
        with self.assertRaises(APIError) as error:
            self.service.delete_policies_id(user=PROFILE, id=first["id"])
        self.assertEqual(error.exception.status, 409)
        with self.assertRaises(APIError):
            upload(title="Bad scope", category="tenant", effectiveFrom="2026-11-04", propertyId="foreign")
        with self.assertRaises(APIError):
            upload(familyId=first["familyId"], expectedVersion=1, effectiveFrom="2026-11-04", category="pets")


if __name__ == "__main__":
    unittest.main()

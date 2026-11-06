"""Contract-driven HTTP adapter. Run from this source checkout: python -m laga.api.

Business implementations live in BackendAPI; transport/auth guards stay here.
The canonical OpenAPI file supplies route IDs and request/response validation.
"""
from __future__ import annotations

import argparse
from datetime import date
import hmac
import inspect
import json
import logging
import math
import os
from pathlib import Path
import re
import secrets
from typing import Any

from fastapi import FastAPI, Request
from jsonschema import Draft202012Validator
from jsonschema.validators import extend
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile
from starlette.exceptions import HTTPException
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse

from .backend_api import APIError, BackendAPI, DEFAULT_DATABASE
from .assistant_integration import call_in_assistant_session
from .paths import resolve_project_path

COOKIE = "laga_session"
MAX_PDF = 10 * 1024 * 1024
MAX_BODY = MAX_PDF + 256 * 1024
MAX_SAFE_INTEGER = 2**53 - 1
ContractValidator = extend(Draft202012Validator, type_checker=Draft202012Validator.TYPE_CHECKER.redefine(
    "integer", lambda checker, value: type(value) is int and abs(value) <= MAX_SAFE_INTEGER))
AUTH_IDS = {"post_auth_login", "get_auth_session", "post_auth_logout"}
GUARDS = {
    "create_property": ("landlord", "policies:write"),
    "post_policies": ("landlord", "policies:write"),
    "delete_policies_id": ("landlord", "policies:write"),
    "post_requests_id_reply": ("landlord", "requests:write"),
    "post_requests": ("tenant", "requests:create"),
}


def default_origins():
    """Use explicit local/preview origins without a developer-specific hostname."""
    configured = os.getenv("LAGA_ALLOWED_ORIGINS")
    if configured is not None:
        return [origin.strip() for origin in configured.split(",")]
    port = os.getenv("LAGA_LOCAL_UI_PORT") or os.getenv("PORT") or "5174"
    if not port.isdecimal() or not 1 <= int(port) <= 65535:
        raise ValueError("UI port must be an integer from 1 through 65535")
    origins = [f"http://localhost:{port}", f"http://127.0.0.1:{port}"]
    domains = [os.getenv("REPLIT_DEV_DOMAIN", ""), *os.getenv("REPLIT_DOMAINS", "").split(",")]
    for domain in filter(None, (value.strip() for value in domains)):
        if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?", domain):
            raise ValueError("Replit domains must be hostnames without a path")
        origins.append("https://"+domain)
    return origins


def load_contract(path: str | Path | None = None) -> dict:
    location = path or os.getenv("LAGA_CONTRACT_PATH") or "contracts/openapi.json"
    return json.loads(resolve_project_path(location).read_text(encoding="utf-8"))


def _check_json_values(value):
    """Reject values that cannot safely cross the JSON/SQLite/browser boundary."""
    pending = [(value, 0)]
    while pending:
        item, depth = pending.pop()
        if depth > 64:
            raise APIError(400, "INVALID_JSON", "JSON nesting exceeds 64 levels.")
        if isinstance(item, dict):
            pending.extend((part, depth+1) for pair in item.items() for part in pair)
        elif isinstance(item, list):
            pending.extend((part, depth+1) for part in item)
        elif isinstance(item, str):
            if any(0xD800 <= ord(c) <= 0xDFFF or (ord(c) < 32 and c not in "\t\r\n") or ord(c) == 127 for c in item):
                raise APIError(422, "VALIDATION_ERROR", "Text contains invalid Unicode or control characters.")
        elif type(item) is int and abs(item) > MAX_SAFE_INTEGER:
            raise APIError(422, "VALIDATION_ERROR", "Integer exceeds the exact range supported by the UI.")
        elif isinstance(item, float) and not math.isfinite(item):
            raise APIError(422, "VALIDATION_ERROR", "Numbers must be finite.")


def validate(contract: dict, schema: dict, value: Any) -> None:
    _check_json_values(value)
    rooted = {"components": contract["components"], **schema}
    errors = list(ContractValidator(rooted).iter_errors(value))
    if errors:
        # Do not echo input values (especially credentials or document text).
        fields = {".".join(map(str, e.absolute_path)) or "body": "Does not match the API contract." for e in errors}
        raise APIError(422, "VALIDATION_ERROR", "Check the submitted fields.", fields)


def _calendar_dates(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"asOf", "effectiveFrom", "effectiveTo"} and item is not None:
                try:
                    if date.fromisoformat(item).isoformat() != item:
                        raise ValueError()
                except (ValueError, TypeError):
                    raise APIError(422, "VALIDATION_ERROR", "Enter a real ISO calendar date.", {key: "Invalid date."})
            _calendar_dates(item)
    elif isinstance(value, list):
        for item in value:
            _calendar_dates(item)


def check_signatures(contract, service):
    """Fail startup when a route, payload field or required argument drifts."""
    for path, methods in contract["paths"].items():
        for verb, operation in methods.items():
            name = operation["operationId"]
            parameters = inspect.signature(getattr(service, name)).parameters
            if any(p.kind in (p.VAR_KEYWORD, p.VAR_POSITIONAL) for p in parameters.values()):
                raise ValueError(f"Use explicit parameters for {name}")
            context = {"session_token", "client_key"} if name == "post_auth_login" else {"session_token"} if name in AUTH_IDS else {"user"}
            path_fields = set(re.findall(r"{([^}]+)}", path))
            content = operation.get("requestBody", {}).get("content", {})
            body_schema = next(iter(content.values()), {}).get("schema", {})
            if "$ref" in body_schema:
                body_schema = contract["components"]["schemas"][body_schema["$ref"].split("/")[-1]]
            fields = set(body_schema.get("properties", {}))
            extra = {"filename", "content_type"} if "multipart/form-data" in content else set()
            expected = context | path_fields | fields | extra
            if set(parameters) != expected:
                raise ValueError(f"Signature mismatch for {verb.upper()} {path}: {set(parameters) ^ expected}")
            required = context | path_fields | set(body_schema.get("required", [])) | extra
            actual_required = {k for k, p in parameters.items() if p.default is inspect.Parameter.empty}
            if actual_required != required:
                raise ValueError(f"Required/default parameter mismatch for {name}")


def _reject_json_constant(value):
    raise ValueError("Nonfinite JSON number")


def _unique_json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON field")
        result[key] = value
    return result


async def _payload(request: Request, operation: dict, contract: dict) -> dict:
    content = operation.get("requestBody", {}).get("content", {})
    limit = MAX_BODY if "multipart/form-data" in content else 64 * 1024
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > limit:
            raise APIError(413, "PAYLOAD_TOO_LARGE", "The upload or request is too large.")
    if not content:
        if raw.strip() not in (b"", b"{}"):
            raise APIError(422, "VALIDATION_ERROR", "This operation takes no request fields.")
        return {}
    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type not in content:
        raise APIError(400, "INVALID_CONTENT_TYPE", "Use the request content type specified by the API contract.")
    schema = content[content_type]["schema"]
    if content_type == "application/json":
        try:
            payload = json.loads(raw, object_pairs_hook=_unique_json_object, parse_constant=_reject_json_constant)
        except (ValueError, UnicodeError, RecursionError):
            raise APIError(400, "INVALID_JSON", "The request body must be valid JSON.")
        validate(contract, schema, payload)
    else:
        async def receive():
            return {"type": "http.request", "body": bytes(raw), "more_body": False}
        bounded = Request(request.scope, receive)
        try:
            async with bounded.form(max_files=1, max_fields=10, max_part_size=8192) as form:
                if len(form.multi_items()) != len(form):
                    raise APIError(422, "VALIDATION_ERROR", "Duplicate form fields are not supported.")
                payload = dict(form)
                upload = payload.get("file")
                if not isinstance(upload, UploadFile):
                    raise APIError(422, "VALIDATION_ERROR", "Choose a PDF file.")
                data = await upload.read(MAX_PDF+1)
                filename, mime = upload.filename or "", upload.content_type or "application/octet-stream"
                if not data or len(data) > MAX_PDF:
                    raise APIError(413 if data else 422, "INVALID_FILE_SIZE", "PDFs must be nonempty and at most 10 MiB.")
                if not filename.lower().endswith(".pdf") or not data.startswith(b"%PDF-") or mime not in {"application/pdf", "application/octet-stream"}:
                    raise APIError(422, "INVALID_PDF", "Choose a file with a PDF name, type and header.")
                payload["file"] = filename
                if "expectedVersion" in payload and isinstance(payload["expectedVersion"], str):
                    if len(payload["expectedVersion"]) > 16 or not re.fullmatch(r"[0-9]+", payload["expectedVersion"]):
                        raise APIError(422, "VALIDATION_ERROR", "expectedVersion must be an integer.")
                    payload["expectedVersion"] = int(payload["expectedVersion"])
                validate(contract, schema, payload)
                payload.update(file=data, filename=filename, content_type=mime)
        except HTTPException:
            raise APIError(400, "INVALID_MULTIPART", "The multipart upload could not be parsed.")
    _calendar_dates(payload)
    for key in ["question", "subject", "message", "reply", "name", "address", "city"]:
        if isinstance(payload.get(key), str) and not payload[key].strip():
            raise APIError(422, "VALIDATION_ERROR", "Text fields must not be blank.", {key: "Enter nonblank text."})
    return payload


def create_app(service: BackendAPI | None = None, *, contract_path=None,
               allowed_origins: list[str] | None = None, secure_cookies: bool = True,
               same_site: str = "lax", bootstrap: bool | None = None) -> FastAPI:
    if same_site not in {"lax", "strict", "none"} or (same_site == "none" and not secure_cookies):
        raise ValueError("SameSite=None requires Secure cookies")
    contract = load_contract(contract_path)
    initialize = (service is None) if bootstrap is None else bootstrap
    service = service or BackendAPI(os.getenv("LAGA_DATABASE", str(DEFAULT_DATABASE)), time_zone=os.getenv("LAGA_TIME_ZONE", "America/New_York"))
    check_signatures(contract, service)
    origins = allowed_origins if allowed_origins is not None else default_origins()
    if not origins or any(o == "*" or o == "null" or not re.fullmatch(r"https?://[^/]+", o) for o in origins):
        raise ValueError("Explicit HTTP(S) origins without paths are required")
    app = FastAPI(title=contract["info"]["title"], docs_url=None, redoc_url=None, openapi_url=None)
    app.state.backend = service
    if initialize and os.getenv("LAGA_BOOTSTRAP", "1") != "0":
        from .bootstrap import bootstrap_database
        app.state.bootstrap = bootstrap_database(service)
        if app.state.bootstrap.get("credentialsPath"):
            logging.getLogger(__name__).warning("Local fictional bootstrap: %s. Sign-in details: %s", app.state.bootstrap["status"], app.state.bootstrap["credentialsPath"])
    else:
        app.state.bootstrap = {"status": "disabled"}
    app.openapi = lambda: contract
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True,
                       allow_methods=["GET", "POST", "DELETE"], allow_headers=["Content-Type", "X-CSRF-Token"])

    def failure(error: APIError):
        return JSONResponse({"error": {"code": error.code, "message": error.message,
                                       "requestId": "req-"+secrets.token_hex(12), "fields": error.fields}},
                            status_code=error.status, headers={"Cache-Control": "no-store"})

    @app.exception_handler(HTTPException)
    async def http_error(request, error):
        return failure(APIError(error.status_code, "NOT_FOUND" if error.status_code == 404 else "HTTP_ERROR", "API route or method is not available."))

    def endpoint(operation):
        async def handle(request: Request):
            try:
                name = operation["operationId"]
                token = request.cookies.get(COOKIE)
                mutation = request.method not in {"GET", "HEAD", "OPTIONS"}
                if mutation and request.headers.get("origin") not in origins:
                    raise APIError(403, "ORIGIN_FORBIDDEN", "This request origin is not allowed.")
                session = await run_in_threadpool(service.get_auth_session, session_token=token)
                user = session["user"]
                if name not in {"post_auth_login", "get_auth_session"}:
                    if not user:
                        raise APIError(401, "UNAUTHENTICATED", "Please sign in to continue.")
                    if mutation and not hmac.compare_digest(request.headers.get("x-csrf-token", "").encode(), session["csrfToken"].encode()):
                        raise APIError(403, "CSRF_INVALID", "Refresh your session and try again.")
                if name in GUARDS:
                    role, permission = GUARDS[name]
                    if user["role"] != role or permission not in user["permissions"]:
                        raise APIError(403, "FORBIDDEN", "You do not have permission for this action.")
                payload = await _payload(request, operation, contract)
                if name == "post_assistant_messages":
                    scope = payload["scope"]
                    if scope["type"] == "portfolio" and (user["role"] != "landlord" or "portfolio:read" not in user["permissions"]):
                        raise APIError(403, "FORBIDDEN", "Portfolio access is restricted.")
                    if (scope["type"] == "lease" and (not scope["id"] or not scope["id"].strip())) or (scope["type"] == "portfolio" and scope["id"] is not None):
                        raise APIError(422, "VALIDATION_ERROR", "Choose a valid lease or portfolio scope.")
                if name == "get_leases_id":
                    permission = "lease:read" if user["role"] == "tenant" else "leases:read"
                    if permission not in user["permissions"]:
                        raise APIError(403, "FORBIDDEN", "Lease access is restricted.")
                cookie = None
                if name == "post_auth_login":
                    result, cookie = await run_in_threadpool(service.post_auth_login, **payload, session_token=token,
                                                            client_key=request.client.host if request.client else "unknown")
                elif name == "get_auth_session":
                    result = session
                elif name == "post_auth_logout":
                    result = await run_in_threadpool(service.post_auth_logout, session_token=token)
                elif name == "post_assistant_messages":
                    result = await run_in_threadpool(
                        call_in_assistant_session, service.post_assistant_messages,
                        session_token=token, user=user, **payload,
                    )
                else:
                    result = await run_in_threadpool(getattr(service, name), user=user, **request.path_params, **payload)
                wrapped = {"data": result}
                try:
                    validate(contract, operation["responses"]["200"]["content"]["application/json"]["schema"], wrapped)
                except APIError:
                    raise APIError(503, "BACKEND_CONTRACT_ERROR", "The backend returned an incompatible response.")
                response = JSONResponse(wrapped, headers={"Cache-Control": "no-store"})
                if cookie:
                    response.set_cookie(COOKIE, cookie, max_age=service.session_seconds, path="/api/v1",
                                        httponly=True, secure=secure_cookies, samesite=same_site)
                elif name == "post_auth_logout" or (name == "get_auth_session" and not user):
                    response.delete_cookie(COOKIE, path="/api/v1", httponly=True, secure=secure_cookies, samesite=same_site)
                return response
            except APIError as error:
                return failure(error)
            except Exception:
                logging.getLogger(__name__).exception("API operation failed: %s", operation["operationId"])
                return failure(APIError(503, "SERVICE_UNAVAILABLE", "The service is temporarily unavailable."))
        return handle

    for path, methods in contract["paths"].items():
        for verb, operation in methods.items():
            app.add_api_route("/api/v1"+path, endpoint(operation), methods=[verb.upper()],
                              operation_id=operation["operationId"], name=operation["operationId"])
    return app


def main():
    parser = argparse.ArgumentParser(description="Run the Laga API scaffold from this source checkout")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8001, type=int)
    parser.add_argument("--insecure-local-cookie", action="store_true", help="HTTP localhost development only")
    parser.add_argument("--no-bootstrap", action="store_true", help="Start with an empty database instead of bundled fictional data")
    args = parser.parse_args()
    if args.insecure_local_cookie and args.host not in {"127.0.0.1", "localhost", "::1"}:
        parser.error("Insecure cookies are restricted to a loopback bind")
    origins = default_origins()
    app = create_app(allowed_origins=origins, secure_cookies=not args.insecure_local_cookie,
                     same_site=os.getenv("LAGA_COOKIE_SAMESITE", "lax"), bootstrap=not args.no_bootstrap)
    import uvicorn
    # Forwarded client addresses are not trusted by default; configure a known proxy in deployment.
    uvicorn.run(app, host=args.host, port=args.port, proxy_headers=False)


if __name__ == "__main__":
    main()

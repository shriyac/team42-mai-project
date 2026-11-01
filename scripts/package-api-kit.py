"""Package current API contract and the built API Explorer without dependencies."""
from pathlib import Path
import hashlib
import json
import zipfile

root = Path(__file__).resolve().parents[1]
version = json.loads((root / "contracts/openapi.json").read_text(encoding="utf-8"))["info"]["version"]
if not (root / "dist/api-docs/index.html").is_file():
    raise SystemExit("Run npm run build before packaging the API kit.")

reference_files = [
    "contracts/openapi.json", "contracts/examples.json", "contracts/integration-examples.json",
    "docs/API_HANDOFF.md", "docs/BACKEND_CONNECTION.md", "docs/INTERFACE_CONTRACT.md", "docs/TEAM_BOUNDARIES.md",
    "frontend/src/services/httpGateway.js", "frontend/src/services/errors.js",
    "frontend/src/lib/apiBase.js", "frontend/src/lib/compliance.js", "frontend/src/lib/features.js", "frontend/.env.example",
    "src/laga/__init__.py", "src/laga/compliance.py", "tests/test_compliance.py",
    f"docs/Laga-Backend-Integration-Guide-v{version}.pdf",
    "docs/integration-guide-examples.json", "docs/integration-guide-manifest.json",
]
# Include tenant lease fixtures in backend handoffs; these are not public UI assets.
reference_files.extend(file.relative_to(root).as_posix()
                       for file in sorted((root / "docs/synthetic-leases").glob("*")) if file.is_file())
for filename in reference_files:
    if not (root / filename).is_file():
        raise SystemExit(f"Missing handoff file: {filename}")

for kit in (False, True):
    name = f"laga-{'api-testing-kit' if kit else 'backend-api'}-v{version}.zip"
    archive = root / name
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        for filename in reference_files:
            bundle.write(root / filename, filename)
        if kit:
            for filename in sorted((root / "dist").rglob("*")):
                if filename.is_file():
                    bundle.write(filename, filename.relative_to(root).as_posix())
            bundle.write(root / "scripts/serve.mjs", "scripts/serve.mjs")
            bundle.writestr("package.json", json.dumps({"name": "laga-api-testing-kit", "private": True,
                "type": "module", "scripts": {"start": "node scripts/serve.mjs"}, "engines": {"node": ">=22"}}, indent=2))
            readme = """# Laga API testing kit

Requires Node.js 22+. Extract this archive, open a terminal in its root and run:

    node scripts/serve.mjs

Open http://localhost:5174/api-docs/ and apply your backend's full API base URL.
No npm installation is needed. Set PORT before starting if 5174 is in use.
Use credentials for your own test backend; all included examples are fictional.

Read docs/BACKEND_CONNECTION.md for testing and same-origin/cross-origin setup.
Import contracts/openapi.json into other OpenAPI 3.1-compatible tools if desired.

The archive contains a built explorer/application preview and reference code,
not an implemented backend. The application preview remains in mock mode.
Explorer target changes do not alter the application. To connect the actual
application, configure and rebuild the original repository as the guide explains.
The static server does not proxy /api; use a full backend URL or a reverse proxy.
Restrict the developer tool's hosting audience according to your environment.
"""
        else:
            readme = """# Laga API handoff

Start with docs/API_HANDOFF.md and docs/BACKEND_CONNECTION.md.
Import contracts/openapi.json into an OpenAPI 3.1-compatible tool.
This archive contains specs, fictional examples and reference code, not a backend.
The companion api-testing-kit archive includes a built interactive API Explorer.
Run frontend compatibility checks from the original application repository.
"""
        bundle.writestr("README.md", readme)
    with zipfile.ZipFile(archive) as bundle:
        assert bundle.testzip() is None
        for filename in reference_files:
            assert bundle.read(filename) == (root / filename).read_bytes()
    print(json.dumps({"archive": name, "bytes": archive.stat().st_size,
                      "sha256": hashlib.sha256(archive.read_bytes()).hexdigest()}))

# A documentation-only package for handing directly to backend implementers.
archive = root / f"laga-backend-documentation-v{version}.zip"
with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
    for filename in reference_files:
        if filename.startswith(("docs/", "contracts/")):
            bundle.write(root / filename, filename)
    bundle.writestr("README.md", f"# Laga backend documentation\n\nStart with docs/Laga-Backend-Integration-Guide-v{version}.pdf.\nThe PDF includes all {len(json.loads((root / 'contracts/openapi.json').read_text(encoding='utf-8'))['paths'])} API routes, the DTO field reference, worked examples and connection instructions.\nUse contracts/openapi.json as the machine-readable transport source of truth.\nExamples are fictional; no real credentials or tenant documents are included.\n")
with zipfile.ZipFile(archive) as bundle:
    assert bundle.testzip() is None
print(json.dumps({"archive": archive.name, "bytes": archive.stat().st_size,
                  "sha256": hashlib.sha256(archive.read_bytes()).hexdigest()}))

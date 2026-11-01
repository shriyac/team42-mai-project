"""Create a source-only Replit import without local dependencies or credentials."""
from pathlib import Path
import hashlib
import json
import tomllib
import zipfile

root = Path(__file__).resolve().parents[1]
config = tomllib.loads((root / ".replit").read_text(encoding="utf-8"))
assert config["modules"] == ["nodejs-22"]
assert config["env"]["PORT"] == str(config["ports"][0]["localPort"])
assert config["ports"][0]["externalPort"] == 80
version = json.loads((root / "package.json").read_text(encoding="utf-8"))["version"]
archive = root / f"laga-replit-source-v{version}.zip"
files = [root / name for name in [".replit", ".gitignore", ".gitattributes", "README.md", "replit.md", "package.json", "package-lock.json", "pyproject.toml", "vite.config.js"]]
for folder in ["frontend", "contracts", "docs", "scripts", "src", "tests"]:
    for file in (root / folder).rglob("*"):
        relative = file.relative_to(root)
        if (not file.is_file() or file.is_symlink()
                or any(part in {"node_modules", "__pycache__"} for part in relative.parts)
                or file.suffix in {".pyc", ".pyo", ".zip"}
                or (file.name.lower().startswith(".env") and file.name != ".env.example")):
            continue
        files.append(file)
with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
    for file in sorted(files):
        bundle.write(file, file.relative_to(root).as_posix())
with zipfile.ZipFile(archive) as bundle:
    assert bundle.testzip() is None
    names = bundle.namelist()
    assert ".replit" in names and "package-lock.json" in names
    assert "docs/Laga-Backend-Integration-Guide-v1.1.0.pdf" in names
    assert not any(name.startswith(("data/", ".git/", "node_modules/", "dist/", "uploads/")) for name in names)
    for name in names:
        assert bundle.read(name) == (root / name).read_bytes()
print(json.dumps({"archive": archive.name, "files": len(files), "bytes": archive.stat().st_size,
                  "sha256": hashlib.sha256(archive.read_bytes()).hexdigest()}))

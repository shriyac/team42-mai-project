"""Package checked-in fictional lease PDFs and extraction answer keys."""
from pathlib import Path
import hashlib
import json
import zipfile

root = Path(__file__).resolve().parents[1]
directory = root / "docs/synthetic-leases"
manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
files = [directory / "README.md", directory / "REVIEW.md", directory / "manifest.json"]
for entry in manifest["documents"]:
    pdf = directory / entry["pdf"]
    if hashlib.sha256(pdf.read_bytes()).hexdigest() != entry["pdfSha256"]:
        raise SystemExit(f"PDF hash mismatch: {pdf.name}")
    text = (directory / entry["text"]).read_bytes()
    variants = [text, text.replace(b"\r\n", b"\n"), text.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")]
    if entry["textSha256"] not in [hashlib.sha256(value).hexdigest() for value in variants]:
        raise SystemExit(f"Text hash mismatch: {entry['text']}")
    files.extend(directory / entry[key] for key in ("pdf", "text", "expectedExtraction", "html"))
archive = root / f"laga-synthetic-lease-corpus-v{manifest['datasetVersion']}.zip"
with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
    for file in sorted(files):
        bundle.write(file, file.relative_to(directory).as_posix())
with zipfile.ZipFile(archive) as bundle:
    assert bundle.testzip() is None
    assert len([name for name in bundle.namelist() if name.endswith(".pdf")]) == 10
print(json.dumps({"archive": archive.name, "files": len(files), "bytes": archive.stat().st_size,
                  "sha256": hashlib.sha256(archive.read_bytes()).hexdigest()}))

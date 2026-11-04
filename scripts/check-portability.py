"""Check sources, runtime location fields and optional PDF/ZIP artifacts for host paths."""
from contextlib import closing
import argparse
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import sqlite3
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PATTERN = re.compile(r"(?<![A-Za-z0-9])(?:[A-Za-z]:[\\/]|file:///(?:[A-Za-z]:|Users/|home/)|/(?:Users|home|workspace)/)")
SKIP = {".git", ".venv", "node_modules", "__pycache__", "data", "dist", "uploads"}
BINARY = {".pdf", ".zip", ".pyc", ".woff2", ".png", ".ico", ".sqlite3"}


def absolute(value):
    return PureWindowsPath(value).is_absolute() or PurePosixPath(value).is_absolute()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts", action="store_true")
    args = parser.parse_args()
    issues = []
    checked = 0
    for path in ROOT.rglob("*"):
        relative = path.relative_to(ROOT)
        if not path.is_file() or any(p in SKIP or p.endswith(".egg-info") for p in relative.parts) or path.suffix.lower() in BINARY:
            continue
        try:
            text = path.read_text(encoding="utf-8-sig")
        except (UnicodeError, OSError):
            continue
        checked += 1
        for number, line in enumerate(text.splitlines(), 1):
            if PATTERN.search(line):
                issues.append(f"{relative.as_posix()}:{number}: embedded absolute workstation path")
    for path in (ROOT / "data").glob("*-bootstrap-login.json"):
        document = json.loads(path.read_text(encoding="utf-8"))
        if absolute(document.get("database", "")):
            issues.append(f"data/{path.name}: database reference is absolute")
    for path in (ROOT / "data").glob("*.sqlite3"):
        with closing(sqlite3.connect(path)) as db:
            exists = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='bootstrap_runs'").fetchone()
            if exists and any(absolute(row[0]) for row in db.execute("SELECT credentials_path FROM bootstrap_runs")):
                issues.append(f"data/{path.name}: bootstrap credential reference is absolute")
    if args.artifacts:
        from pypdf import PdfReader
        for path in (ROOT / "docs").rglob("*.pdf"):
            reader = PdfReader(path)
            values = [str(reader.metadata)]
            for page in reader.pages:
                values.append(page.extract_text() or "")
                for annotation in page.get("/Annots", []):
                    action = annotation.get_object().get("/A", {})
                    if action:
                        values.append(str(action.get_object().get("/URI", "")))
            if any(PATTERN.search(v) for v in values):
                issues.append(f"{path.relative_to(ROOT).as_posix()}: embedded path in PDF")
        for path in ROOT.glob("laga-*.zip"):
            with zipfile.ZipFile(path) as archive:
                for name in archive.namelist():
                    parts = PurePosixPath(name).parts
                    if absolute(name) or ".." in parts or (parts and parts[0] in {"data", ".venv", "node_modules", ".git"}) or any(p.endswith(".egg-info") for p in parts):
                        issues.append(f"{path.name}: nonportable/private archive member")
                    if Path(name).suffix.lower() in BINARY:
                        continue
                    try:
                        text = archive.read(name).decode("utf-8-sig")
                    except UnicodeError:
                        continue
                    if PATTERN.search(text):
                        issues.append(f"{path.name}: embedded path in {name}")
    if issues:
        for issue in issues:
            print("FAIL " + issue)
        raise SystemExit(1)
    print(f"PASS {checked} source/text files, runtime path metadata" + (", PDF metadata/text/links and handoff archives" if args.artifacts else ""))


if __name__ == "__main__":
    main()

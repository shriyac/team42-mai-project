"""Independently compare every lease page across Markdown, HTML and extracted PDF text.
Requires pypdf (python -m pip install pypdf). No documents are modified.
"""
from pathlib import Path
from html.parser import HTMLParser
from decimal import Decimal, ROUND_HALF_UP
from datetime import date, timedelta
import calendar
import hashlib
import json
import re
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / "docs/synthetic-leases"

class Paragraphs(HTMLParser):
    def __init__(self):
        super().__init__()
        self.pages = []
        self.active = False
    def handle_starttag(self, tag, attrs):
        if tag == "section":
            self.pages.append([])
        if tag == "p":
            self.active = True
            self.pages[-1].append("")
    def handle_endtag(self, tag):
        if tag == "p":
            self.active = False
    def handle_data(self, data):
        if self.active:
            self.pages[-1][-1] += data

def norm(value):
    return re.sub(r"\s+", "", value)

def prorate(rent, occupied, days):
    return int((Decimal(rent) * occupied / days).quantize(Decimal("1"), rounding=ROUND_HALF_UP))

def main():
    manifest = json.loads((DIRECTORY / "manifest.json").read_text(encoding="utf-8"))
    assert len(manifest["documents"]) == 10
    expected_files = {"README.md", "REVIEW.md", "manifest.json"}
    for entry in manifest["documents"]:
        expected_files.update(entry[k] for k in ("pdf", "html", "text", "expectedExtraction"))
        record = json.loads((DIRECTORY / entry["expectedExtraction"]).read_text(encoding="utf-8"))
        text = (DIRECTORY / entry["text"]).read_text(encoding="utf-8")
        html = (DIRECTORY / entry["html"]).read_text(encoding="utf-8")
        for value in (text, html):
            assert not re.search(r"[?\ufffd]|TODO|TBD|FIXME|\u00e2\u20ac", value), entry["text"] + ": unresolved placeholder or encoding"
        parser = Paragraphs()
        parser.feed(html)
        pages = re.split(r"^# Page \d+ / .*\n", text, flags=re.M)[1:]
        reader = PdfReader(DIRECTORY / entry["pdf"])
        assert len(reader.pages) == len(pages) == len(parser.pages) == entry["pages"] == 12
        for i, (page, paragraphs, pdf) in enumerate(zip(pages, parser.pages, reader.pages), 1):
            body = page.strip().split("\n\n", 1)[1].removesuffix("\n---").strip()
            assert norm(body) == norm("\n\n".join(paragraphs)), (entry["text"], i, "HTML differs")
            extracted = norm(pdf.extract_text())
            for paragraph in paragraphs:
                assert norm(paragraph) in extracted, (entry["pdf"], i, "PDF missing paragraph", paragraph[:80])
            assert norm(record["tenant"]["name"]) in extracted
            assert record["leaseId"] in extracted
        t = record["terms"]
        start, end = date.fromisoformat(t["startDate"]), date.fromisoformat(t["endDate"])
        sd, ed = calendar.monthrange(start.year, start.month)[1], calendar.monthrange(end.year, end.month)[1]
        assert t["firstRentCents"] == prorate(t["rentCents"], sd-start.day+1, sd)
        assert t["lastRentCents"] == prorate(t["rentCents"], end.day, ed)
        assert t["firstLateFeeDate"] == (start+timedelta(days=5)).isoformat()
        assert t["lastRentDueDate"] == end.replace(day=1).isoformat()
        assert t["noticeDeadline"] == (end-timedelta(days=t["noticeDays"])).isoformat()
        assert record["tenant"]["grossAnnualIncomeCents"] == 12*record["tenant"]["grossMonthlyIncomeCents"]
        assert t["monthlyPetRentCents"] == 0 and record["utilities"]["monthlyLaundryFeeCents"] == 0
        assert record["paymentInstructions"]["payee"] == record["landlord"]["organization"]
        assert record["paymentInstructions"]["livePaymentEnabled"] is False
        assert record["banking"]["accountHolder"] == record["tenant"]["name"]
        for key, value in (("text", entry["textSha256"]), ("pdf", entry["pdfSha256"])):
            data = (DIRECTORY / entry[key]).read_bytes()
            variants = [data] if key == "pdf" else [data, data.replace(b"\r\n", b"\n"), data.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")]
            assert value in [hashlib.sha256(v).hexdigest() for v in variants]
        assert record["signatureStatus"] == "unsigned_test_fixture"
        assert record["legalReviewStatus"] == "not_performed"
        print(f"PASS {entry['leaseId']}: 12 complete PDF/HTML/Markdown pages, JSON arithmetic and identity")
    actual = {p.name for p in DIRECTORY.iterdir() if p.is_file()}
    assert actual == expected_files, ("Unexpected or missing corpus files", actual ^ expected_files)
    print("PASS all 43 corpus files accounted for; 120 pages cross-checked")

if __name__ == "__main__":
    main()

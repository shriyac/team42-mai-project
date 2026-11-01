"""Server-side NC source cache and fail-closed review boundary.

Not an HTTP service or legal reasoning engine. The ingestion/assistant service
must call review() with extracted PDF text or the final answer before release.
"""
from contextlib import closing
from .paths import resolve_project_path
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
import json
import sqlite3
from urllib.request import Request, build_opener, HTTPRedirectHandler


SOURCES = (
    "https://www.ncleg.gov/EnactedLegislation/Statutes/HTML/ByChapter/Chapter_42.html",
    "https://ncdoj.gov/protecting-consumers/home-repair-and-products/renting-a-home/",
)


class ReviewUnavailable(Exception):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ReviewUnavailable("Official source redirected; review source configuration.")


def fetch_official(url):
    if url not in SOURCES:
        raise ReviewUnavailable("Unconfigured government source.")
    request = Request(url, headers={"User-Agent": "Laga-policy-review/0.1"})
    with build_opener(NoRedirect).open(request, timeout=20) as response:
        content = response.read(5_000_001)
        if len(content) > 5_000_000 or response.headers.get_content_type() != "text/html":
            raise ReviewUnavailable("Invalid government source response.")
        text = content.decode("utf-8")
        if "42-42" not in text and "rights and responsibilities" not in text.lower():
            raise ReviewUnavailable("Government source content could not be verified.")
        return text


class LawCache:
    """SQLite cache shared by uploads and answers; refresh at most daily.

    A failed refresh never serves stale law. BEGIN IMMEDIATE deduplicates initial
    fetch/refresh across processes using the same database.
    """

    def __init__(self, database, fetcher=fetch_official, now=None):
        self.database = str(resolve_project_path(database))
        self.fetcher = fetcher
        self.now = now or (lambda: datetime.now(timezone.utc))
        with closing(sqlite3.connect(self.database)) as db, db:
            db.execute("CREATE TABLE IF NOT EXISTS laws (state TEXT PRIMARY KEY, payload TEXT NOT NULL)")

    def get(self, state):
        if state != "NC":
            raise ReviewUnavailable("No reviewed government sources configured for this state.")
        with closing(sqlite3.connect(self.database, timeout=60)) as db, db:
            db.execute("BEGIN IMMEDIATE")
            now = self.now()
            row = db.execute("SELECT payload FROM laws WHERE state=?", (state,)).fetchone()
            if row:
                snapshot = json.loads(row[0])
                if datetime.fromisoformat(snapshot["fetchedAt"]) <= now < datetime.fromisoformat(snapshot["expiresAt"]):
                    return snapshot
            try:
                documents = [{"url": url, "content": self.fetcher(url)} for url in SOURCES]
                if any(not item["content"].strip() for item in documents):
                    raise ReviewUnavailable("Empty government source.")
            except Exception as error:
                raise ReviewUnavailable("Government sources unavailable; review blocked.") from error
            now = self.now()
            revision = sha256(json.dumps(documents, sort_keys=True).encode()).hexdigest()
            snapshot = {"state": state, "revision": revision, "fetchedAt": now.isoformat(),
                        "expiresAt": (now + timedelta(days=1)).isoformat(), "documents": documents}
            db.execute("INSERT OR REPLACE INTO laws VALUES (?, ?)", (state, json.dumps(snapshot)))
            return snapshot


def review(cache, *, state, property_states, text, as_of, kind, scope_key, reviewer=None):
    """Every new document/final answer gets its own content-bound assessment.

    reviewer is trusted server code, never a client verdict. It must evaluate all
    clauses/claims, exceptions, effective dates, federal/local applicability and
    prompt injection. Missing coverage or unresolved conflicts must not pass.
    """
    if date.fromisoformat(as_of).isoformat() != as_of:
        raise ValueError("Use a YYYY-MM-DD reference date.")
    if not scope_key or not isinstance(scope_key, str):
        raise ValueError("A property or lease scope is required.")
    if kind not in {"policy", "answer"} or not text.strip():
        raise ValueError("Review requires policy/answer content.")
    if not property_states or any(value != state for value in property_states):
        raise ValueError("Policy state must match every scoped property.")
    result = {"status": "unavailable", "state": state,
              "contentHash": sha256(text.encode()).hexdigest(), "asOf": as_of, "kind": kind, "scopeKey": scope_key}
    try:
        snapshot = cache.get(state)
    except (ReviewUnavailable, sqlite3.Error, ValueError, KeyError, TypeError):
        return result
    result.update(lawRevision=snapshot["revision"], checkedAt=cache.now().isoformat(),
                  expiresAt=snapshot["expiresAt"], status="pending")
    if reviewer is None:
        return result
    if cache.now() >= datetime.fromisoformat(snapshot["expiresAt"]):
        result["status"] = "unavailable"
        return result
    try:
        assessment = reviewer(text=text, laws=snapshot, as_of=as_of, kind=kind, scope_key=scope_key)
        if cache.now() >= datetime.fromisoformat(snapshot["expiresAt"]):
            result["status"] = "unavailable"
            return result
        citations = assessment.get("citations", [])
        allowed = {document["url"] for document in snapshot["documents"]}
        if (assessment.get("status") == "passed" and assessment.get("coverageComplete") is True
                and citations and all(c.get("url") in allowed and c.get("section") for c in citations)
                and not assessment.get("findings")):
            result.update(status="passed", citations=citations)
        elif assessment.get("status") == "conflict":
            result.update(status="conflict", findings=assessment.get("findings", []))
    except Exception:
        result["status"] = "unavailable"
    return result

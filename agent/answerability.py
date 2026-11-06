"""Conservative, deterministic question/statement relations, not similarity scores.

Only reviewed lease intents are supported. Unknown intents and absent values
abstain. These rules do not provide general semantic entailment; generators
must additionally remain extractive and pass citation provenance validation.
"""

import re

from .evidence import source_text


def has(pattern, text):
    return bool(re.search(pattern, text, re.I | re.S))


def requirements(question):
    q = question.casefold()
    # Sensitive value requests must not fall through to generic utility terms.
    if has(r"\b(password|passphrase|credentials?|access code|pin)\b", q):
        return ("verified_access_value",)
    intents = []
    if has(r"\b(expir\w*|end date)\b|lease.{0,25}\bend\b|\bend\b.{0,25}lease", q):
        intents.append("lease_end")
    if has(r"\b(pets?|cat|dog)\b", q):
        intents.append("pets")
    if has(r"\bdeposit\b", q):
        intents.append("deposit_amount" if has(r"how much|amount", q) else "deposit_terms")
    if has(r"\blate[\s-]+(?:fees?|charges?|payment)|\boverdue\b", q):
        intents.append("late_fee")
    elif has(r"\b(?:monthly rent|rent amount)\b|how much.{0,20}\brent\b", q):
        intents.append("rent_amount")
    elif has(r"\brent\b.{0,30}\bdue\b", q):
        intents.append("rent_due")
    if has(r"\bquiet hours\b", q):
        intents.append("quiet_hours")
    # An additional explicit question may not disappear behind a known topic.
    parts = re.split(r"\band\s+(?=(?:what|when|where|who|how|which|is|are|does|do|can)\b)", q)
    if len(parts) > 1 and any(not requirements(p.strip()) for p in parts):
        return ()
    return tuple(dict.fromkeys(intents))


RELATIONS = {
    "lease_end": r"\bend date(?:\s*\(inclusive\))?\s*:\s*\d{4}-\d\d-\d\d|"
                 r"\blease\s+(?:term\s+)?(?:ends?|expires?)\s+(?:on\s+)?\d|"
                 r"\bterm\s*:\s*\d{4}-\d\d-\d\d\s+(?:through|to)\s+\d{4}-\d\d-\d\d",
    "pets": r"\b(?:one|two|no|\d+)\s+(?:ordinary\s+)?pets?\b.{0,80}"
            r"\b(?:allowed|permitted|prohibited)\b|"
            r"\bpets?\s+(?:is|are)\s+(?:not\s+)?(?:allowed|permitted|prohibited)\b|"
            r"(?:^|\n)[☑✓✔\s-]*pets?\s+(?:not\s+)?allowed\b",
    "deposit_amount": r"\b(?:security\s+)?deposit\b.{0,45}\$\s*\d",
    "deposit_terms": r"\bdeposit\b.{0,180}\b(?:refund\w*|return\w*|deduct\w*|damage|held)\b|"
                     r"\b(?:refund\w*|return\w*|deduct\w*)\b.{0,100}\bdeposit\b|"
                     r"\bdocumented damage\b.{0,100}\bdeducted\b",
    "late_fee": r"\blate\s+(?:fee|charge)s?\b.{0,100}(?:\$\s*\d|\d+(?:\.\d+)?\s*%)|"
                r"\bno\s+late\s+fee\b",
    "rent_amount": r"\bmonthly\s+rent\b.{0,45}\$\s*\d|\brent\s*:\s*\$\s*\d",
    "rent_due": r"\b(?:rent|payment)\b.{0,65}\bdue\b.{0,50}(?:\d|first|day one)",
    "quiet_hours": r"\bquiet hours\b.{0,50}\b(?:\d{1,2}\s*(?:p\.?m\.?|a\.?m\.?)|"
                   r"\d{1,2}:\d{2})",
}
UNAVAILABLE = r"\b(?:not (?:provided|specified|stated|known)|unspecified|unavailable|unknown|blank)\b"


def covers(intent, text):
    # Access credentials are outside the reviewed lease-answer intent set.
    if intent not in RELATIONS:
        return False
    # A literal quote of an unchecked template option is not an operative term.
    # Incomplete line fragments must not become claims just because they carry
    # a subject and verb. Prefer abstention to dropping attached conditions.
    if "☐" in text or has(r"\b(?:in|of|to|for|the|a|an|and|or|with|under|subject to)\s*$", text):
        return False
    if has(r"\bthe timeframe mentioned\b", text):
        return False
    if has(UNAVAILABLE, text) and not has(r"\b(?:allowed|permitted|deducted|ends?|end date)\b", text):
        return False
    return has(RELATIONS[intent], text)


def excerpts(question, document):
    """Return exact contiguous source excerpts with their original PDF pages."""
    wanted = requirements(question)
    if not wanted:
        return []
    meta = document.metadata
    spans = meta.get("source_spans")
    if not isinstance(spans, (list, tuple)) or not spans:
        spans = [{"text": source_text(document),
                  "page_number": meta.get("page_number", meta.get("page"))}]
    selected = []
    for span in spans:
        text = span.get("text", "")
        if not isinstance(text, str):
            continue
        for paragraph in re.split(r"\n\s*\n", text):
            # Do not dump long multi-clause chunks. Each candidate remains an
            # exact substring of one verified source span on one PDF page.
            candidates = [paragraph.strip()]
            if len(paragraph) > 900:
                # Preserve wrapped PDF lines within a sentence. Splitting at
                # line breaks can sever "returned ... in [conditions]" clauses.
                candidates = [x.strip() for x in re.split(r"(?<=[.!?])\s+(?=[A-Z])", paragraph)]
            for quote in candidates:
                covered = {intent for intent in wanted if covers(intent, quote)}
                if quote and len(quote) <= 900 and covered:
                    selected.append((quote, span.get("page_number"), covered))
    return selected


def select(question, documents):
    """Choose at most one exact passage per required intent; require all parts."""
    wanted = requirements(question)
    if not wanted:
        return []
    candidates = [(doc, quote, page, covered) for doc in documents
                  for quote, page, covered in excerpts(question, doc)]
    chosen, satisfied = [], set()
    for intent in wanted:
        if intent in satisfied:
            continue
        matches = [c for c in candidates if intent in c[3]]
        if not matches:
            return []
        # Prefer concise clauses, not a similarity score or token overlap.
        best = min(matches, key=lambda c: len(c[1]))
        chosen.append(best[:3])
        satisfied.update(best[3])
    return chosen


def answerable(question, quotes):
    wanted = requirements(question)
    return bool(wanted) and all(any(covers(intent, quote) for quote in quotes) for intent in wanted)


def insufficient_message(question):
    if has(r"\b(?:wi[\s-]?fi|wireless|internet)\b", question) and has(r"\bpassword\b", question):
        return "The available lease documents do not provide a verified Wi-Fi password."
    return ""

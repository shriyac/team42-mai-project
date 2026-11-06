"""Conservative deterministic extraction, not monetary calculation.

Only explicit amounts and dates are accepted. A monthly due day alone does not
identify a rental installment. Neither ``as_of`` nor the payment month is used
to guess the installment due date. Unrecognized wording needs clarification.
"""

from datetime import date, datetime
from decimal import Decimal
import re

from tools.fee_calculator import FeeCalculationInput

from .evidence import source_text
from .state import LAGAState


NUMBER = r"-?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?"
NUMBER_END = r"(?![\w]|[,.]\d)"
RENT = re.compile(
    rf"\bmonthly\s+(?:base\s+)?rent(?:\s+(?:is|of))?\s*[:=]?\s*"
    rf"(?:USD\s*|\$\s*)?({NUMBER}){NUMBER_END}", re.I,
)
FEE_CLAUSE = re.compile(
    r"\b(?:no\s+)?late\s+(?:fee|charge)\b.*?(?=\.(?:\s|$)|;|\n|$)", re.I,
)
FLAT = re.compile(rf"(?:\$|USD)\s*({NUMBER}){NUMBER_END}", re.I)
PERCENT = re.compile(rf"(?<![\w.,])({NUMBER}){NUMBER_END}\s*%")
AMBIGUOUS = re.compile(
    r"\b(?:may|up to|between|or|whichever|discretion|varies|unless|if|after|"
    r"before|only|when|not|no|waived|prohibited|daily|per day)\b", re.I,
)
DATE_TOKEN = (
    r"(?:\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{4}|"
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|"
    r"Dec(?:ember)?)\s+\d{1,2},?\s+\d{4})"
)
PAYMENT_DATE = re.compile(
    rf"\b(?:paid|payment(?:\s+was)?\s+made|payment\s+date)"
    rf"\s*(?:on|is|:)?\s*({DATE_TOKEN})", re.I,
)
DUE_DATE = re.compile(
    rf"\b(?:rent\s+)?due(?:\s+date)?\s*(?:on|is|:|=)?\s*({DATE_TOKEN})", re.I,
)
DUE_DAY = re.compile(
    r"\b(?:due|payable)\s+(?:on|by)\s+(?:the\s+)?"
    r"(first|second|third|fourth|fifth|\d{1,2}(?:st|nd|rd|th)?)"
    r"(?:\s+day)?\s+(?:of\s+)?(?:each|every)\s+(?:calendar\s+)?month\b", re.I,
)
_FEE = r"late\s+(?:fee|charge)"
_ACTION = r"(?:charged|assessed|paid)"
_PRIOR = r"(?:(?:already|previously)\s+)?"
_PERSON = r"(?:(?:i|we)\s+)?"
_TERM = rf"(?:(?:a|the)\s+)?{_FEE}"
_PASSIVE = rf"(?:has\s+{_PRIOR}been|was(?:\s+(?:already|previously))?)"
_THIS_INSTALLMENT = r"(?:\s+for\s+this\s+(?:rental\s+)?installment)?"
_NEGATIVE_FEE_STATUS = re.compile(
    rf"(?:no\s+{_FEE}\s+(?:{_PASSIVE}\s+)?{_ACTION}|"
    rf"{_PERSON}(?:have|has)\s+not\s+{_PRIOR}(?:been\s+)?{_ACTION}\s+{_TERM}|"
    rf"{_TERM}\s+(?:has\s+not\s+{_PRIOR}been|was\s+not)\s+{_ACTION})"
    rf"{_THIS_INSTALLMENT}"
)
_POSITIVE_FEE_STATUS = re.compile(
    rf"(?:{_TERM}\s+{_PASSIVE}\s+{_ACTION}|"
    rf"{_PERSON}(?:have\s+)?{_PRIOR}paid\s+{_TERM}|"
    rf"{_PERSON}(?:have\s+{_PRIOR}been|was(?:\s+(?:already|previously))?)"
    rf"\s+(?:charged|assessed)\s+{_TERM}|"
    rf"(?:already|previously)\s+{_ACTION}\s+{_TERM})"
    rf"{_THIS_INSTALLMENT}"
)
_UNCERTAIN_FEE_STATUS = re.compile(
    r"\b(?:whether|if|unless|suppose|assuming|would|could|might|maybe|perhaps|"
    r"possibly|unsure|uncertain|don't know|do not know|not sure|not certain)\b"
)


def _prior_fee_status(question: str) -> bool | None:
    """Parse complete reviewed assertions; None means clarification, not False.

    Never search for a positive assertion inside a negated or qualified clause.
    Both contradictory assertions and unrecognized status wording fail closed.
    This deliberately does not attempt general natural-language interpretation.
    """
    text = re.sub(r"\s+", " ", question.replace("’", "'")).casefold()
    for contraction, expanded in (
        ("haven't", "have not"), ("hasn't", "has not"),
        ("wasn't", "was not"), ("i've", "i have"),
    ):
        text = re.sub(rf"\b{contraction}\b", expanded, text)
    if _UNCERTAIN_FEE_STATUS.search(text):
        return None
    statuses = set()
    for sentence in re.split(r"[.!?;]+", text):
        if not re.search(rf"\b{_FEE}\b", sentence) or not re.search(rf"\b{_ACTION}\b", sentence):
            continue
        for clause in re.split(r"\s+(?:and|but|however|yet)\s+|,\s*", sentence):
            clause = clause.strip()
            if _NEGATIVE_FEE_STATUS.fullmatch(clause):
                statuses.add(False)
            elif _POSITIVE_FEE_STATUS.fullmatch(clause):
                statuses.add(True)
            elif clause:
                # Only explicit rent/payment dates may accompany an assertion.
                # Do not discard qualifiers or elliptical contradictions such
                # as "but not paid" or ", not really".
                if re.search(rf"\b{_FEE}\b", clause) or not (
                    PAYMENT_DATE.search(clause) or DUE_DATE.search(clause)
                ):
                    return None
    return next(iter(statuses)) if len(statuses) == 1 else None


def _date_token(value):
    try:
        return date.fromisoformat(value)
    except ValueError:
        pass
    for fmt in ("%m/%d/%Y", "%B %d, %Y", "%B %d %Y", "%b %d, %Y", "%b %d %Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    return None


def _dates(pattern, text):
    return {_date_token(m.group(1)) for m in pattern.finditer(text)}


def extract_fee_input(state: LAGAState):
    """Return validated-shape calculator inputs or explicit extraction errors."""
    text = "\n".join(
        source_text(doc) for bundle in state.get("retrieved_evidence", [])
        for doc in bundle.get("documents", [])
    )
    question = state.get("question", "")
    errors = []
    rents = {Decimal(m.group(1).replace(",", "")) for m in RENT.finditer(text)}
    if len(rents) != 1:
        errors.append("A single explicit monthly rent amount is required.")

    payments = _dates(PAYMENT_DATE, question)
    due_dates = _dates(DUE_DATE, text + "\n" + question)
    if len(payments) != 1 or None in payments:
        errors.append("A single valid explicit payment date is required.")
    if len(due_dates) != 1 or None in due_dates:
        errors.append(
            "Specify the installment's exact due date; a monthly due day or as_of "
            "date alone does not identify the installment."
        )
    due = next(iter(due_dates)) if len(due_dates) == 1 else None
    due_days = set()
    for match in DUE_DAY.finditer(text):
        word = match.group(1).lower()
        ordinal = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5}.get(word)
        due_days.add(ordinal if ordinal else int(re.sub(r"(st|nd|rd|th)$", "", word)))
    if len(due_days) > 1 or (due and due_days and due.day not in due_days):
        errors.append("The installment due date conflicts with the retrieved due-day terms.")

    charged = _prior_fee_status(question)
    if charged is None:
        errors.append("Clarify whether a late fee has already been charged for this installment.")

    flat, percentages = set(), set()
    for match in FEE_CLAUSE.finditer(text):
        clause = match.group()
        clause_flat = {Decimal(m.group(1).replace(",", "")) for m in FLAT.finditer(clause)}
        clause_percentages = {Decimal(m.group(1)) for m in PERCENT.finditer(clause)}
        if (clause_flat or clause_percentages) and AMBIGUOUS.search(clause):
            errors.append("The contractual late-fee clause is conditional or ambiguous.")
        if clause_percentages and not re.search(
            r"%\s+of\s+(?:the\s+)?monthly\s+rent\b", clause, re.I
        ):
            errors.append("The fee percentage must explicitly apply to monthly rent.")
        flat.update(clause_flat)
        percentages.update(clause_percentages)
    if len(flat) > 1 or len(percentages) > 1:
        errors.append("The retrieved contractual late-fee terms conflict.")
    if errors:
        return None, list(dict.fromkeys(errors))

    # Missing fee terms and mixed flat/percentage terms are deliberately passed
    # unchanged to the existing calculator's clarification result.
    return FeeCalculationInput(
        monthly_rent=next(iter(rents)),
        due_date=due,
        payment_date=next(iter(payments)),
        contractual_fee_amount=next(iter(flat)) if flat else None,
        contractual_fee_percentage=next(iter(percentages)) if percentages else None,
        fee_already_charged=charged,
    ), []

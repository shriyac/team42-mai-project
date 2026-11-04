"""Deterministic North Carolina monthly-rent late-fee calculation.

Money inputs and outputs are USD per monthly rental installment. Monetary values
are accepted as ``Decimal``, integer-dollar values, or decimal strings with at
most two fractional digits. Floats are rejected to avoid binary rounding.
Percentage inputs use percentage points: ``Decimal("5")`` means 5%.

This module applies only the timing and maximum-fee rules specified for
N.C. General Statute §42-46. It does not decide whether a contract term is
legally enforceable or give legal advice.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any


CENT = Decimal("0.01")
FIFTEEN_DOLLARS = Decimal("15.00")
FIVE_PERCENT = Decimal("0.05")
ONE_HUNDRED = Decimal("100")
ELIGIBILITY_DELAY_DAYS = 5

STATUS_FEE_CALCULATED = "fee_calculated"
STATUS_NOT_LATE = "not_late"
STATUS_NOT_YET_ELIGIBLE = "not_yet_eligible"
STATUS_ALREADY_CHARGED = "already_charged"
STATUS_CLARIFICATION_REQUIRED = "clarification_required"
STATUS_INVALID_INPUT = "invalid_input"


@dataclass(frozen=True)
class FeeCalculationInput:
    """Structured inputs for one monthly rental installment.

    ``contractual_fee_amount`` and ``contractual_fee_percentage`` are mutually
    exclusive. Provide exactly one when a fee calculation is eligible. The
    percentage is expressed in percentage points (for example, 5 means 5%).
    """

    monthly_rent: Decimal | int | str
    due_date: date | str
    payment_date: date | str
    contractual_fee_amount: Decimal | int | str | None = None
    contractual_fee_percentage: Decimal | int | str | None = None
    fee_already_charged: bool = False


@dataclass(frozen=True)
class FeeCalculationResult:
    """Result for one installment; all monetary values are USD.

    ``calculated_late_fee`` is the additional fee permitted by the supplied
    contract term after applying the statutory maximum. It is zero when no
    additional fee is due, and ``None`` when validation prevents calculation.
    ``statutory_maximum`` is ``None`` only when monthly rent is invalid.
    """

    status: str
    calculated_late_fee: Decimal | None
    statutory_maximum: Decimal | None
    formula: str
    inputs: dict[str, Any]
    explanation: str
    validation_errors: tuple[str, ...] = ()
    currency: str = "USD"
    monetary_unit: str = "USD per monthly rental installment"

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly result with monetary amounts as decimal strings."""

        return {
            "status": self.status,
            "currency": self.currency,
            "monetary_unit": self.monetary_unit,
            "calculated_late_fee": _money_string(self.calculated_late_fee),
            "statutory_maximum": _money_string(self.statutory_maximum),
            "formula": self.formula,
            "inputs": dict(self.inputs),
            "explanation": self.explanation,
            "validation_errors": list(self.validation_errors),
        }


def calculate_late_fee(inputs: FeeCalculationInput) -> FeeCalculationResult:
    """Calculate a monthly-rent late fee without using an LLM.

    A fee is eligible only when the payment date is at least five calendar
    days after the due date. An eligible amount is the lesser of the
    unambiguous contractual fee and ``max($15, 5% of monthly rent)``.
    """

    if not isinstance(inputs, FeeCalculationInput):
        raise TypeError("inputs must be a FeeCalculationInput instance")

    input_snapshot = _input_snapshot(inputs)
    errors: list[str] = []

    monthly_rent = _parse_money(
        inputs.monthly_rent, "monthly_rent", errors, must_be_positive=True
    )
    due_date = _parse_date(inputs.due_date, "due_date", errors)
    payment_date = _parse_date(inputs.payment_date, "payment_date", errors)
    fee_amount = _parse_money(
        inputs.contractual_fee_amount,
        "contractual_fee_amount",
        errors,
        optional=True,
    )
    fee_percentage = _parse_decimal(
        inputs.contractual_fee_percentage,
        "contractual_fee_percentage",
        errors,
        optional=True,
    )

    if inputs.contractual_fee_percentage is not None and fee_percentage is not None:
        if fee_percentage < 0:
            errors.append("contractual_fee_percentage must not be negative.")

    if not isinstance(inputs.fee_already_charged, bool):
        errors.append("fee_already_charged must be a boolean.")

    statutory_maximum = (
        max(FIFTEEN_DOLLARS, _round_money(monthly_rent * FIVE_PERCENT))
        if monthly_rent is not None
        else None
    )
    cap_formula = "max(USD 15.00, 5% × monthly_rent)"

    if errors:
        return FeeCalculationResult(
            status=STATUS_INVALID_INPUT,
            calculated_late_fee=None,
            statutory_maximum=statutory_maximum,
            formula="No fee calculation performed because one or more inputs are invalid.",
            inputs=input_snapshot,
            explanation="Correct the validation errors before calculating a late fee.",
            validation_errors=tuple(errors),
        )

    # The preceding validation guarantees these values are available.
    assert monthly_rent is not None
    assert due_date is not None
    assert payment_date is not None
    assert statutory_maximum is not None

    if inputs.fee_already_charged:
        return FeeCalculationResult(
            status=STATUS_ALREADY_CHARGED,
            calculated_late_fee=Decimal("0.00"),
            statutory_maximum=statutory_maximum,
            formula="additional_fee = USD 0.00 because a fee was already charged for this installment",
            inputs=input_snapshot,
            explanation=(
                "A late fee has already been charged for this rental installment; "
                "no duplicate fee is calculated."
            ),
        )

    days_late = (payment_date - due_date).days
    if days_late <= 0:
        return FeeCalculationResult(
            status=STATUS_NOT_LATE,
            calculated_late_fee=Decimal("0.00"),
            statutory_maximum=statutory_maximum,
            formula="additional_fee = USD 0.00 because payment_date is on or before due_date",
            inputs=input_snapshot,
            explanation="Payment was made on or before the due date, so no late fee is due.",
        )

    if days_late < ELIGIBILITY_DELAY_DAYS:
        eligible_date = due_date + timedelta(days=ELIGIBILITY_DELAY_DAYS)
        return FeeCalculationResult(
            status=STATUS_NOT_YET_ELIGIBLE,
            calculated_late_fee=Decimal("0.00"),
            statutory_maximum=statutory_maximum,
            formula=(
                "additional_fee = USD 0.00 until payment_date is at least "
                "due_date + 5 calendar days"
            ),
            inputs=input_snapshot,
            explanation=(
                f"Payment is {days_late} calendar day(s) late. A fee is not eligible "
                f"before {eligible_date.isoformat()}, five calendar days after the due date."
            ),
        )

    has_flat_fee = inputs.contractual_fee_amount is not None
    has_percentage_fee = inputs.contractual_fee_percentage is not None
    if has_flat_fee == has_percentage_fee:
        return FeeCalculationResult(
            status=STATUS_CLARIFICATION_REQUIRED,
            calculated_late_fee=None,
            statutory_maximum=statutory_maximum,
            formula=(
                "contractual_fee must be exactly one of a flat USD amount or "
                "a percentage of monthly_rent; statutory_maximum = "
                f"{cap_formula}"
            ),
            inputs=input_snapshot,
            explanation=(
                "The contractual late-fee term is missing or ambiguous. Provide "
                "exactly one flat fee amount or percentage; no contractual term "
                "has been inferred."
            ),
            validation_errors=(
                "Provide exactly one of contractual_fee_amount or "
                "contractual_fee_percentage.",
            ),
        )

    if has_flat_fee:
        # A non-None fee amount has already passed money validation.
        assert fee_amount is not None
        contractual_fee = fee_amount
        formula = (
            "calculated_late_fee = min(contractual_fee_amount, "
            "max(USD 15.00, 5% × monthly_rent))"
        )
        fee_term = f"the contractual flat fee of USD {_money_string(fee_amount)}"
    else:
        # A non-None percentage has already passed decimal validation.
        assert fee_percentage is not None
        contractual_fee = _round_money(monthly_rent * fee_percentage / ONE_HUNDRED)
        formula = (
            "calculated_late_fee = min(monthly_rent × "
            "contractual_fee_percentage / 100, "
            "max(USD 15.00, 5% × monthly_rent))"
        )
        fee_term = (
            f"the contractual fee of {_decimal_string(fee_percentage)}% "
            "of monthly rent"
        )

    calculated_fee = min(contractual_fee, statutory_maximum)
    capped = contractual_fee > statutory_maximum
    explanation = (
        f"Payment is {days_late} calendar days late and meets the five-day "
        f"eligibility threshold. The {fee_term} is "
        f"USD {_money_string(contractual_fee)} before applying the statutory "
        f"maximum of USD {_money_string(statutory_maximum)}."
    )
    if capped:
        explanation += (
            f" The contractual amount exceeds the statutory maximum, so the "
            f"calculated late fee is capped at USD {_money_string(calculated_fee)}."
        )
    else:
        explanation += (
            f" The calculated late fee is USD {_money_string(calculated_fee)}."
        )

    return FeeCalculationResult(
        status=STATUS_FEE_CALCULATED,
        calculated_late_fee=calculated_fee,
        statutory_maximum=statutory_maximum,
        formula=formula,
        inputs=input_snapshot,
        explanation=explanation,
    )


def _parse_money(
    value: Any,
    field_name: str,
    errors: list[str],
    *,
    optional: bool = False,
    must_be_positive: bool = False,
) -> Decimal | None:
    amount = _parse_decimal(value, field_name, errors, optional=optional)
    if amount is None:
        return None
    if amount != amount.quantize(CENT):
        errors.append(f"{field_name} must not have more than two decimal places.")
        return None
    if amount < 0 or (must_be_positive and amount == 0):
        comparison = "greater than zero" if must_be_positive else "zero or greater"
        errors.append(f"{field_name} must be {comparison}.")
        return None
    return amount.quantize(CENT)


def _parse_decimal(
    value: Any,
    field_name: str,
    errors: list[str],
    *,
    optional: bool = False,
) -> Decimal | None:
    if value is None:
        if not optional:
            errors.append(f"{field_name} is required.")
        return None
    if isinstance(value, bool) or isinstance(value, float):
        errors.append(
            f"{field_name} must be a Decimal, integer, or decimal string; floats are not accepted."
        )
        return None
    if not isinstance(value, (Decimal, int, str)):
        errors.append(f"{field_name} must be a Decimal, integer, or decimal string.")
        return None
    try:
        parsed = Decimal(value) if not isinstance(value, Decimal) else value
    except (InvalidOperation, ValueError):
        errors.append(f"{field_name} must be a valid decimal number.")
        return None
    if not parsed.is_finite():
        errors.append(f"{field_name} must be finite.")
        return None
    return parsed


def _parse_date(value: Any, field_name: str, errors: list[str]) -> date | None:
    if isinstance(value, datetime):
        errors.append(f"{field_name} must be a calendar date, not a datetime.")
        return None
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        errors.append(f"{field_name} must be a date or an ISO date string (YYYY-MM-DD).")
        return None
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        errors.append(f"{field_name} must be a valid ISO date (YYYY-MM-DD).")
        return None
    if parsed.isoformat() != value:
        errors.append(f"{field_name} must use the YYYY-MM-DD date format.")
        return None
    return parsed


def _round_money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def _money_string(value: Decimal | None) -> str | None:
    return None if value is None else format(value.quantize(CENT), ".2f")


def _decimal_string(value: Decimal) -> str:
    return format(value, "f")


def _input_snapshot(inputs: FeeCalculationInput) -> dict[str, Any]:
    return {
        "monthly_rent_usd": _display_input(inputs.monthly_rent),
        "due_date": _display_input(inputs.due_date),
        "payment_date": _display_input(inputs.payment_date),
        "contractual_fee_amount_usd": _display_input(inputs.contractual_fee_amount),
        "contractual_fee_percentage": _display_input(inputs.contractual_fee_percentage),
        "fee_already_charged": _display_input(inputs.fee_already_charged),
    }


def _display_input(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    if value is None or isinstance(value, (str, int, bool)):
        return value
    return repr(value)

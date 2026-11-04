from datetime import date
from decimal import Decimal

import pytest

from tools.fee_calculator import (
    FeeCalculationInput,
    STATUS_ALREADY_CHARGED,
    STATUS_CLARIFICATION_REQUIRED,
    STATUS_FEE_CALCULATED,
    STATUS_INVALID_INPUT,
    STATUS_NOT_LATE,
    STATUS_NOT_YET_ELIGIBLE,
    calculate_late_fee,
)


def make_input(**overrides):
    values = {
        "monthly_rent": Decimal("1000.00"),
        "due_date": date(2026, 1, 1),
        "payment_date": date(2026, 1, 6),
        "contractual_fee_amount": Decimal("20.00"),
    }
    values.update(overrides)
    return FeeCalculationInput(**values)


def test_on_time_payment_has_no_late_fee():
    result = calculate_late_fee(
        make_input(payment_date=date(2026, 1, 1))
    )

    assert result.status == STATUS_NOT_LATE
    assert result.calculated_late_fee == Decimal("0.00")
    assert result.statutory_maximum == Decimal("50.00")
    assert result.validation_errors == ()


def test_payment_before_five_calendar_days_is_not_fee_eligible():
    result = calculate_late_fee(
        make_input(payment_date=date(2026, 1, 5))
    )

    assert result.status == STATUS_NOT_YET_ELIGIBLE
    assert result.calculated_late_fee == Decimal("0.00")
    assert "2026-01-06" in result.explanation


def test_qualifying_late_payment_calculates_flat_contract_fee():
    result = calculate_late_fee(make_input())

    assert result.status == STATUS_FEE_CALCULATED
    assert result.calculated_late_fee == Decimal("20.00")
    assert result.statutory_maximum == Decimal("50.00")
    assert "min(contractual_fee_amount" in result.formula


def test_percentage_fee_uses_monthly_rent_and_percentage_points():
    result = calculate_late_fee(
        make_input(
            monthly_rent=Decimal("800.00"),
            contractual_fee_amount=None,
            contractual_fee_percentage=Decimal("2.5"),
        )
    )

    assert result.status == STATUS_FEE_CALCULATED
    assert result.calculated_late_fee == Decimal("20.00")
    assert result.statutory_maximum == Decimal("40.00")
    assert "contractual_fee_percentage / 100" in result.formula


def test_flat_fee_is_capped_at_fifteen_dollar_floor_for_low_rent():
    result = calculate_late_fee(
        make_input(
            monthly_rent=Decimal("200.00"),
            contractual_fee_amount=Decimal("25.00"),
        )
    )

    assert result.calculated_late_fee == Decimal("15.00")
    assert result.statutory_maximum == Decimal("15.00")
    assert "capped" in result.explanation


def test_flat_fee_is_capped_at_five_percent_for_high_rent():
    result = calculate_late_fee(
        make_input(
            monthly_rent=Decimal("1000.00"),
            contractual_fee_amount=Decimal("75.00"),
        )
    )

    assert result.calculated_late_fee == Decimal("50.00")
    assert result.statutory_maximum == Decimal("50.00")


def test_missing_contractual_fee_requires_clarification():
    result = calculate_late_fee(
        make_input(contractual_fee_amount=None)
    )

    assert result.status == STATUS_CLARIFICATION_REQUIRED
    assert result.calculated_late_fee is None
    assert result.validation_errors
    assert "no contractual term has been inferred" in result.explanation


def test_previously_charged_installment_has_no_duplicate_fee():
    result = calculate_late_fee(
        make_input(fee_already_charged=True)
    )

    assert result.status == STATUS_ALREADY_CHARGED
    assert result.calculated_late_fee == Decimal("0.00")
    assert "no duplicate fee" in result.explanation


@pytest.mark.parametrize(
    ("field", "value", "error_fragment"),
    [
        ("due_date", "2026-02-30", "due_date"),
        ("payment_date", "not-a-date", "payment_date"),
        ("monthly_rent", Decimal("-1.00"), "monthly_rent"),
        ("contractual_fee_amount", Decimal("-0.01"), "contractual_fee_amount"),
    ],
)
def test_invalid_dates_and_negative_amounts_are_reported(field, value, error_fragment):
    result = calculate_late_fee(make_input(**{field: value}))

    assert result.status == STATUS_INVALID_INPUT
    assert result.calculated_late_fee is None
    assert result.validation_errors
    assert any(error_fragment in error for error in result.validation_errors)


def test_both_contract_fee_forms_are_ambiguous():
    result = calculate_late_fee(
        make_input(contractual_fee_percentage=Decimal("5"))
    )

    assert result.status == STATUS_CLARIFICATION_REQUIRED
    assert result.calculated_late_fee is None
    assert "exactly one" in result.validation_errors[0]


def test_result_serializes_money_as_decimal_strings_with_units():
    result = calculate_late_fee(make_input())
    payload = result.to_dict()

    assert payload["calculated_late_fee"] == "20.00"
    assert payload["statutory_maximum"] == "50.00"
    assert payload["currency"] == "USD"
    assert payload["monetary_unit"] == "USD per monthly rental installment"


def test_float_money_is_rejected_to_avoid_binary_rounding():
    result = calculate_late_fee(make_input(monthly_rent=1000.0))

    assert result.status == STATUS_INVALID_INPUT
    assert any("floats are not accepted" in error for error in result.validation_errors)

from decimal import Decimal

from app.analytics.baseline import compare_failure_periods
from app.models import PaymentStatus


def test_baseline_comparison_calculates_absolute_relative_and_affected_value(
    transaction_factory,
) -> None:
    baseline = [transaction_factory() for _ in range(96)] + [
        transaction_factory(status=PaymentStatus.FAILED) for _ in range(4)
    ]
    current = [transaction_factory() for _ in range(90)] + [
        transaction_factory(status=PaymentStatus.FAILED, amount="50") for _ in range(10)
    ]
    comparison = compare_failure_periods(
        baseline, current, segment={"card_network": "MASTERCARD", "issuer_country": "US"}
    )
    assert comparison.baseline_failure_rate == Decimal("0.040000")
    assert comparison.current_failure_rate == Decimal("0.100000")
    assert comparison.absolute_difference == Decimal("0.060000")
    assert comparison.relative_percentage_change == Decimal("1.500000")
    assert comparison.affected_attempted_payment_value["GBP"] == Decimal("500.000000")
    assert comparison.transaction_count == 100
    assert comparison.failed_transaction_count == 10


def test_zero_baseline_rate_has_no_relative_change(transaction_factory) -> None:
    comparison = compare_failure_periods(
        [transaction_factory() for _ in range(10)],
        [transaction_factory(status=PaymentStatus.FAILED)],
    )
    assert comparison.relative_percentage_change is None


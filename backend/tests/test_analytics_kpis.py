from decimal import Decimal

from app.analytics.kpis import calculate_kpis
from app.models import PaymentStatus


def test_kpis_use_documented_denominators_and_currency_buckets(transaction_factory) -> None:
    transactions = [
        transaction_factory(
            amount="100", processing_fee="2", provider_fee="1", other_cost="0.5", refund_amount="10"
        ),
        transaction_factory(
            amount="50", processing_fee="1", provider_fee="0.5", other_cost="0.25", dispute_amount="50"
        ),
        transaction_factory(amount="25", status=PaymentStatus.FAILED),
        transaction_factory(
            amount="20", currency="USD", processing_fee="0.3", provider_fee="0.2", other_cost="0.1"
        ),
    ]

    metrics = calculate_kpis(transactions)

    assert metrics.transaction_count == 4
    assert metrics.successful_transaction_count == 3
    assert metrics.failed_transaction_count == 1
    assert metrics.attempted_payment_value == {
        "GBP": Decimal("175.000000"),
        "USD": Decimal("20.000000"),
    }
    assert metrics.successful_payment_value["GBP"] == Decimal("150.000000")
    assert metrics.failed_attempted_payment_value["GBP"] == Decimal("25.000000")
    assert metrics.success_rate == Decimal("0.750000")
    assert metrics.failure_rate == Decimal("0.250000")
    assert metrics.average_transaction_value["GBP"] == Decimal("58.333333")
    assert metrics.refund_amount["GBP"] == Decimal("10.000000")
    assert metrics.refund_rate == Decimal("0.333333")
    assert metrics.dispute_amount["GBP"] == Decimal("50.000000")
    assert metrics.dispute_rate == Decimal("0.333333")
    assert metrics.processing_fees["GBP"] == Decimal("3.000000")
    assert metrics.provider_fees["GBP"] == Decimal("1.500000")
    assert metrics.total_payment_cost["GBP"] == Decimal("5.250000")
    assert metrics.effective_payment_cost_percentage["GBP"] == Decimal("0.035000")


def test_empty_dataset_has_safe_zero_denominators() -> None:
    metrics = calculate_kpis([])
    assert metrics.transaction_count == 0
    assert metrics.success_rate == 0
    assert metrics.failure_rate == 0
    assert metrics.refund_rate == 0
    assert metrics.dispute_rate == 0
    assert metrics.attempted_payment_value == {}
    assert metrics.effective_payment_cost_percentage == {}


def test_no_successful_value_returns_undefined_effective_cost(transaction_factory) -> None:
    metrics = calculate_kpis(
        [transaction_factory(amount="25", status=PaymentStatus.FAILED)]
    )
    assert metrics.successful_payment_value == {}
    assert metrics.effective_payment_cost_percentage["GBP"] is None


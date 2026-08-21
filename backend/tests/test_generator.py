from datetime import datetime, timezone
from decimal import Decimal

from app.models import CardNetwork, PaymentProvider, PaymentStatus
from app.synthetic.config import AnomalyRule, AnomalyType, GenerationConfig
from app.synthetic.generator import generate_transactions


def test_generator_returns_exact_requested_count() -> None:
    transactions = list(generate_transactions(GenerationConfig(count=317, seed=1)))
    assert len(transactions) == 317
    assert len({item.id for item in transactions}) == 317


def test_generated_required_fields_and_amounts_are_valid() -> None:
    transactions = list(generate_transactions(GenerationConfig(count=500, seed=2)))
    assert all(item.id and item.merchant_id and item.provider_transaction_id for item in transactions)
    assert all(item.amount >= 0 for item in transactions)
    assert all(item.gross_amount >= 0 and item.net_amount >= 0 for item in transactions)
    assert all(item.status in PaymentStatus for item in transactions)


def test_fixed_seed_is_reproducible() -> None:
    config = GenerationConfig(count=100, seed=42)
    first = [item.model_dump_json() for item in generate_transactions(config)]
    second = [item.model_dump_json() for item in generate_transactions(config)]
    assert first == second


def test_different_seed_changes_output() -> None:
    first = next(generate_transactions(GenerationConfig(count=1, seed=42)))
    second = next(generate_transactions(GenerationConfig(count=1, seed=43)))
    assert first.id != second.id


def test_network_failure_anomaly_increases_target_failure_rate() -> None:
    start = datetime(2026, 4, 1, tzinfo=timezone.utc)
    end = datetime(2026, 7, 1, tzinfo=timezone.utc)
    anomaly = AnomalyRule(
        type=AnomalyType.NETWORK_SPECIFIC_FAILURE,
        probability=0.55,
        card_network=CardNetwork.MASTERCARD,
        issuer_country="US",
    )
    transactions = list(
        generate_transactions(
            GenerationConfig(count=12_000, seed=7, start_at=start, end_at=end, anomalies=[anomaly])
        )
    )
    target = [
        item
        for item in transactions
        if item.card_network == CardNetwork.MASTERCARD and item.issuer_country == "US"
    ]
    control = [
        item
        for item in transactions
        if item.card_network == CardNetwork.MASTERCARD and item.issuer_country == "GB"
    ]
    target_rate = sum(item.status == PaymentStatus.FAILED for item in target) / len(target)
    control_rate = sum(item.status == PaymentStatus.FAILED for item in control) / len(control)
    assert len(target) > 500
    assert target_rate > 0.45
    assert target_rate > control_rate + 0.35


def test_fee_refund_and_dispute_anomalies_apply() -> None:
    rules = [
        AnomalyRule(
            type=AnomalyType.HIGH_PROVIDER_FEES,
            multiplier=4,
            provider=PaymentProvider.PAYPAL,
        ),
        AnomalyRule(type=AnomalyType.REFUND_SPIKE, probability=1, provider=PaymentProvider.PAYPAL),
        AnomalyRule(type=AnomalyType.DISPUTE_SPIKE, probability=1, provider=PaymentProvider.PAYPAL),
    ]
    transactions = list(generate_transactions(GenerationConfig(count=2_000, seed=9, anomalies=rules)))
    target = [
        item
        for item in transactions
        if item.provider == PaymentProvider.PAYPAL and item.status == PaymentStatus.SUCCEEDED
    ]
    assert target
    assert all(item.provider_fee >= Decimal("0.01") for item in target)
    assert all(item.refund_amount > 0 for item in target)
    assert all(item.dispute_amount > 0 for item in target)


def test_failure_spike_and_country_failure_rules_apply() -> None:
    rules = [
        AnomalyRule(type=AnomalyType.FAILURE_SPIKE, probability=1, provider=PaymentProvider.STRIPE),
        AnomalyRule(type=AnomalyType.COUNTRY_SPECIFIC_FAILURE, probability=1, issuer_country="DE"),
    ]
    transactions = list(generate_transactions(GenerationConfig(count=1_500, seed=13, anomalies=rules)))
    stripe = [item for item in transactions if item.provider == PaymentProvider.STRIPE]
    germany = [item for item in transactions if item.issuer_country == "DE"]
    assert stripe and germany
    assert all(item.status == PaymentStatus.FAILED for item in stripe)
    assert all(item.status == PaymentStatus.FAILED for item in germany)


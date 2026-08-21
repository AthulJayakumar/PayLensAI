from datetime import datetime, timezone

from app.insights.engine import InsightEngine
from app.insights.models import InsightType
from app.synthetic.config import GenerationConfig, default_anomalies
from app.synthetic.generator import generate_transactions


def _has_segment(insights, insight_type: InsightType, **expected: str) -> bool:
    return any(
        insight.type == insight_type
        and all(insight.segment.get(key) == value for key, value in expected.items())
        for insight in insights
    )


def test_100k_synthetic_dataset_discovers_injected_anomalies_without_row_labels() -> None:
    transactions = list(
        generate_transactions(
            GenerationConfig(count=100_000, seed=20_260_822, anomalies=default_anomalies())
        )
    )
    insights = InsightEngine().analyse(
        transactions,
        current_start=datetime(2026, 6, 16, tzinfo=timezone.utc),
        current_end=datetime(2026, 7, 1, tzinfo=timezone.utc),
    )

    assert len(transactions) == 100_000
    assert _has_segment(insights, InsightType.FAILURE_SPIKE, provider="STRIPE")
    assert _has_segment(
        insights,
        InsightType.FAILURE_SPIKE,
        card_network="MASTERCARD",
        issuer_country="US",
    )
    assert _has_segment(insights, InsightType.FAILURE_SPIKE, issuer_country="DE")
    assert _has_segment(insights, InsightType.HIGH_PAYMENT_COST, provider="PAYPAL")
    assert _has_segment(insights, InsightType.PROVIDER_COST_DIFFERENCE, provider="PAYPAL")
    assert _has_segment(
        insights, InsightType.REFUND_SPIKE, card_network="VISA", issuer_country="GB"
    )
    assert _has_segment(
        insights, InsightType.DISPUTE_SPIKE, provider="ADYEN", issuer_country="US"
    )

    # Obvious unrelated findings would be false positives for the injected profile.
    assert not _has_segment(insights, InsightType.HIGH_PAYMENT_COST, provider="STRIPE")
    assert not _has_segment(insights, InsightType.HIGH_PAYMENT_COST, provider="ADYEN")
    assert not _has_segment(insights, InsightType.REFUND_SPIKE, card_network="MASTERCARD")
    assert not _has_segment(insights, InsightType.DISPUTE_SPIKE, provider="PAYPAL")
    assert not any(
        insight.type == InsightType.PAYMENT_METHOD_UNDERPERFORMANCE for insight in insights
    )


from decimal import Decimal

import pytest

from app.analytics.models import KPIMetrics
from app.insights.detectors import (
    DisputeSpikeDetector,
    FailureSpikeDetector,
    HighFailureSegmentDetector,
    HighPaymentCostDetector,
    PaymentMethodUnderperformanceDetector,
    ProviderCostDifferenceDetector,
    RefundSpikeDetector,
)
from app.insights.models import DetectionContext, InsightType


def metrics(
    *,
    count: int = 1000,
    failures: int = 30,
    refund_rate: str = "0.01",
    dispute_rate: str = "0.002",
    cost_rate: str = "0.018",
) -> KPIMetrics:
    successes = count - failures
    attempted = Decimal(count * 100)
    successful_value = Decimal(successes * 100)
    failed_value = Decimal(failures * 100)
    cost = successful_value * Decimal(cost_rate)
    return KPIMetrics(
        transaction_count=count,
        successful_transaction_count=successes,
        failed_transaction_count=failures,
        attempted_payment_value={"GBP": attempted},
        successful_payment_value={"GBP": successful_value},
        failed_attempted_payment_value={"GBP": failed_value},
        success_rate=Decimal(successes) / Decimal(count) if count else Decimal("0"),
        failure_rate=Decimal(failures) / Decimal(count) if count else Decimal("0"),
        average_transaction_value={"GBP": Decimal("100")} if count else {},
        refund_amount={"GBP": successful_value * Decimal(refund_rate)},
        refund_rate=Decimal(refund_rate),
        dispute_amount={"GBP": successful_value * Decimal(dispute_rate)},
        dispute_rate=Decimal(dispute_rate),
        processing_fees={"GBP": cost / 2},
        provider_fees={"GBP": cost / 2},
        other_costs={"GBP": Decimal("0")},
        total_payment_cost={"GBP": cost},
        effective_payment_cost_percentage={"GBP": Decimal(cost_rate)},
    )


def context(segment: dict[str, str], baseline: KPIMetrics, current: KPIMetrics) -> DetectionContext:
    return DetectionContext(segment=segment, baseline=baseline, current=current)


@pytest.fixture
def overall() -> DetectionContext:
    return context({}, metrics(count=5000, failures=200), metrics(count=1000, failures=40))


def test_failure_spike_detector(overall) -> None:
    target = context(
        {"card_network": "MASTERCARD", "issuer_country": "US"},
        metrics(count=2000, failures=60),
        metrics(count=500, failures=60),
    )
    insights = FailureSpikeDetector().detect([target], overall)
    assert len(insights) == 1
    assert insights[0].type == InsightType.FAILURE_SPIKE
    assert insights[0].baseline_value == Decimal("0.03")
    assert insights[0].current_value == Decimal("0.12")
    assert insights[0].affected_attempted_value["GBP"] == Decimal("6000")


def test_high_failure_segment_detector(overall) -> None:
    target = context(
        {"issuer_country": "US"}, metrics(), metrics(count=500, failures=75)
    )
    insights = HighFailureSegmentDetector().detect([target], overall)
    assert len(insights) == 1
    assert insights[0].type == InsightType.HIGH_FAILURE_SEGMENT


def test_high_payment_cost_detector(overall) -> None:
    target = context(
        {"provider": "PAYPAL"}, metrics(cost_rate="0.018"), metrics(cost_rate="0.031")
    )
    insights = HighPaymentCostDetector().detect([target], overall)
    assert len(insights) == 1
    assert insights[0].segment == {"provider": "PAYPAL", "currency": "GBP"}


def test_provider_cost_difference_detector(overall) -> None:
    contexts = [
        context({"provider": "ADYEN"}, metrics(), metrics(cost_rate="0.015")),
        context({"provider": "STRIPE"}, metrics(), metrics(cost_rate="0.018")),
        context({"provider": "PAYPAL"}, metrics(), metrics(cost_rate="0.027")),
    ]
    insights = ProviderCostDifferenceDetector().detect(contexts, overall)
    assert len(insights) == 1
    assert insights[0].segment["provider"] == "PAYPAL"
    assert insights[0].evidence["lowest_cost_provider"] == "ADYEN"


def test_refund_spike_detector(overall) -> None:
    target = context(
        {"card_network": "VISA", "issuer_country": "GB"},
        metrics(refund_rate="0.015"),
        metrics(count=500, failures=20, refund_rate="0.12"),
    )
    insights = RefundSpikeDetector().detect([target], overall)
    assert len(insights) == 1
    assert insights[0].type == InsightType.REFUND_SPIKE


def test_dispute_spike_detector(overall) -> None:
    target = context(
        {"provider": "ADYEN", "issuer_country": "US"},
        metrics(dispute_rate="0.003"),
        metrics(count=500, failures=20, dispute_rate="0.045"),
    )
    insights = DisputeSpikeDetector().detect([target], overall)
    assert len(insights) == 1
    assert insights[0].type == InsightType.DISPUTE_SPIKE


def test_payment_method_underperformance_detector(overall) -> None:
    target = context(
        {"payment_method": "BANK_TRANSFER"},
        metrics(),
        metrics(count=500, failures=45),
    )
    insights = PaymentMethodUnderperformanceDetector().detect([target], overall)
    assert len(insights) == 1
    assert insights[0].evidence["benchmark"] == "all_current_payment_methods"


@pytest.mark.parametrize(
    "detector",
    [
        FailureSpikeDetector(),
        HighFailureSegmentDetector(),
        RefundSpikeDetector(),
        DisputeSpikeDetector(),
        PaymentMethodUnderperformanceDetector(),
    ],
)
def test_small_sample_obvious_false_positive_is_suppressed(detector, overall) -> None:
    tiny = context(
        {"payment_method": "CARD"},
        metrics(count=50, failures=1),
        metrics(count=10, failures=9, refund_rate="0.8", dispute_rate="0.8"),
    )
    assert detector.detect([tiny], overall) == []


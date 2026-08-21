"""Built-in deterministic insight detectors."""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from app.insights.base import Detector, build_insight, currency_value, relative_change
from app.insights.models import DetectionContext, Insight, InsightType


MIN_CURRENT_SAMPLE = 100
MIN_BASELINE_SAMPLE = 200


def _failure_candidate(context: DetectionContext) -> bool:
    """Select useful localisation levels while avoiding nested alert floods."""

    dimensions = set(context.segment)
    if dimensions in ({"provider"}, {"issuer_country"}):
        return context.current.transaction_count >= 500
    if dimensions == {"card_network", "issuer_country"}:
        return context.current.transaction_count >= 300
    return False


def _failure_rate_threshold(context: DetectionContext) -> Decimal:
    dimensions = set(context.segment)
    if dimensions == {"provider"}:
        return Decimal("0.10")
    if dimensions == {"issuer_country"}:
        return Decimal("0.11")
    return Decimal("0.12")


class FailureSpikeDetector(Detector):
    insight_type = InsightType.FAILURE_SPIKE

    def detect(self, contexts: Sequence[DetectionContext], overall: DetectionContext) -> list[Insight]:
        insights = []
        for context in contexts:
            if not _failure_candidate(context):
                continue
            baseline = context.baseline.failure_rate
            current = context.current.failure_rate
            change = relative_change(current, baseline)
            minimum_rate = _failure_rate_threshold(context)
            if (
                context.current.transaction_count < MIN_CURRENT_SAMPLE
                or context.baseline.transaction_count < MIN_BASELINE_SAMPLE
                or current < minimum_rate
                or current - baseline < Decimal("0.02")
                or change is None
                or change < Decimal("0.50")
            ):
                continue
            insights.append(
                build_insight(
                    insight_type=self.insight_type,
                    segment=context.segment,
                    metric="failure_rate",
                    baseline_value=baseline,
                    current_value=current,
                    affected_values=context.current.failed_attempted_payment_value,
                    affected_attempted_value=context.current.failed_attempted_payment_value,
                    transaction_count=context.current.transaction_count,
                    affected_transaction_count=context.current.failed_transaction_count,
                    evidence={
                        "baseline_transaction_count": context.baseline.transaction_count,
                        "baseline_failed_transaction_count": context.baseline.failed_transaction_count,
                    },
                )
            )
        return insights


class HighFailureSegmentDetector(Detector):
    insight_type = InsightType.HIGH_FAILURE_SEGMENT

    def detect(self, contexts: Sequence[DetectionContext], overall: DetectionContext) -> list[Insight]:
        insights = []
        for context in contexts:
            if not _failure_candidate(context):
                continue
            current = context.current.failure_rate
            baseline = context.baseline.failure_rate
            if context.current.transaction_count < 150 or current < _failure_rate_threshold(context):
                continue
            insights.append(
                build_insight(
                    insight_type=self.insight_type,
                    segment=context.segment,
                    metric="failure_rate",
                    baseline_value=baseline,
                    current_value=current,
                    affected_values=context.current.failed_attempted_payment_value,
                    affected_attempted_value=context.current.failed_attempted_payment_value,
                    transaction_count=context.current.transaction_count,
                    affected_transaction_count=context.current.failed_transaction_count,
                )
            )
        return insights


class HighPaymentCostDetector(Detector):
    insight_type = InsightType.HIGH_PAYMENT_COST

    def detect(self, contexts: Sequence[DetectionContext], overall: DetectionContext) -> list[Insight]:
        insights = []
        for context in contexts:
            if set(context.segment) != {"provider"} or context.current.transaction_count < 200:
                continue
            for currency, current in context.current.effective_payment_cost_percentage.items():
                if current is None or current < Decimal("0.023"):
                    continue
                baseline = context.baseline.effective_payment_cost_percentage.get(currency)
                cost = currency_value(context.current.total_payment_cost, currency)
                insights.append(
                    build_insight(
                        insight_type=self.insight_type,
                        segment={**context.segment, "currency": currency},
                        metric="effective_payment_cost_percentage",
                        baseline_value=baseline,
                        current_value=current,
                        affected_values=cost,
                        affected_payment_cost=cost,
                        transaction_count=context.current.transaction_count,
                        affected_transaction_count=context.current.successful_transaction_count,
                    )
                )
        return insights


class ProviderCostDifferenceDetector(Detector):
    insight_type = InsightType.PROVIDER_COST_DIFFERENCE

    def detect(self, contexts: Sequence[DetectionContext], overall: DetectionContext) -> list[Insight]:
        provider_contexts = [
            context
            for context in contexts
            if set(context.segment) == {"provider"} and context.current.transaction_count >= 200
        ]
        currencies = sorted(
            {
                currency
                for context in provider_contexts
                for currency, value in context.current.effective_payment_cost_percentage.items()
                if value is not None
            }
        )
        insights = []
        for currency in currencies:
            peers = [
                (context, context.current.effective_payment_cost_percentage.get(currency))
                for context in provider_contexts
            ]
            peers = [(context, value) for context, value in peers if value is not None]
            if len(peers) < 2:
                continue
            best_context, best_rate = min(peers, key=lambda item: item[1])
            for context, current in peers:
                change = relative_change(current, best_rate)
                if (
                    context is best_context
                    or current - best_rate < Decimal("0.006")
                    or change is None
                    or change < Decimal("0.30")
                ):
                    continue
                cost = currency_value(context.current.total_payment_cost, currency)
                insights.append(
                    build_insight(
                        insight_type=self.insight_type,
                        segment={**context.segment, "currency": currency},
                        metric="effective_payment_cost_percentage",
                        baseline_value=best_rate,
                        current_value=current,
                        affected_values=cost,
                        affected_payment_cost=cost,
                        transaction_count=context.current.transaction_count,
                        affected_transaction_count=context.current.successful_transaction_count,
                        evidence={"lowest_cost_provider": best_context.segment["provider"]},
                    )
                )
        return insights


class RefundSpikeDetector(Detector):
    insight_type = InsightType.REFUND_SPIKE

    def detect(self, contexts: Sequence[DetectionContext], overall: DetectionContext) -> list[Insight]:
        insights = []
        for context in contexts:
            if set(context.segment) != {"card_network", "issuer_country"}:
                continue
            baseline = context.baseline.refund_rate
            current = context.current.refund_rate
            change = relative_change(current, baseline)
            if (
                context.current.successful_transaction_count < MIN_CURRENT_SAMPLE
                or context.baseline.successful_transaction_count < MIN_BASELINE_SAMPLE
                or current < Decimal("0.06")
                or current - baseline < Decimal("0.03")
                or change is None
                or change < Decimal("1")
            ):
                continue
            refund_count = round(current * context.current.successful_transaction_count)
            insights.append(
                build_insight(
                    insight_type=self.insight_type,
                    segment=context.segment,
                    metric="refund_rate",
                    baseline_value=baseline,
                    current_value=current,
                    affected_values=context.current.refund_amount,
                    affected_refund_amount=context.current.refund_amount,
                    transaction_count=context.current.successful_transaction_count,
                    affected_transaction_count=refund_count,
                )
            )
        return insights


class DisputeSpikeDetector(Detector):
    insight_type = InsightType.DISPUTE_SPIKE

    def detect(self, contexts: Sequence[DetectionContext], overall: DetectionContext) -> list[Insight]:
        insights = []
        for context in contexts:
            if set(context.segment) != {"provider", "issuer_country"}:
                continue
            baseline = context.baseline.dispute_rate
            current = context.current.dispute_rate
            change = relative_change(current, baseline)
            if (
                context.current.successful_transaction_count < MIN_CURRENT_SAMPLE
                or context.baseline.successful_transaction_count < MIN_BASELINE_SAMPLE
                or current < Decimal("0.02")
                or current - baseline < Decimal("0.01")
                or change is None
                or change < Decimal("1")
            ):
                continue
            dispute_count = round(current * context.current.successful_transaction_count)
            insights.append(
                build_insight(
                    insight_type=self.insight_type,
                    segment=context.segment,
                    metric="dispute_rate",
                    baseline_value=baseline,
                    current_value=current,
                    affected_values=context.current.dispute_amount,
                    affected_dispute_amount=context.current.dispute_amount,
                    transaction_count=context.current.successful_transaction_count,
                    affected_transaction_count=dispute_count,
                )
            )
        return insights


class PaymentMethodUnderperformanceDetector(Detector):
    insight_type = InsightType.PAYMENT_METHOD_UNDERPERFORMANCE

    def detect(self, contexts: Sequence[DetectionContext], overall: DetectionContext) -> list[Insight]:
        benchmark = overall.current.failure_rate
        insights = []
        for context in contexts:
            if set(context.segment) != {"payment_method"}:
                continue
            current = context.current.failure_rate
            change = relative_change(current, benchmark)
            if (
                context.current.transaction_count < 200
                or current < Decimal("0.06")
                or current - benchmark < Decimal("0.02")
                or change is None
                or change < Decimal("0.40")
            ):
                continue
            insights.append(
                build_insight(
                    insight_type=self.insight_type,
                    segment=context.segment,
                    metric="failure_rate",
                    baseline_value=benchmark,
                    current_value=current,
                    affected_values=context.current.failed_attempted_payment_value,
                    affected_attempted_value=context.current.failed_attempted_payment_value,
                    transaction_count=context.current.transaction_count,
                    affected_transaction_count=context.current.failed_transaction_count,
                    evidence={"benchmark": "all_current_payment_methods"},
                )
            )
        return insights


BUILT_IN_DETECTORS: tuple[type[Detector], ...] = (
    FailureSpikeDetector,
    HighFailureSegmentDetector,
    HighPaymentCostDetector,
    ProviderCostDifferenceDetector,
    RefundSpikeDetector,
    DisputeSpikeDetector,
    PaymentMethodUnderperformanceDetector,
)

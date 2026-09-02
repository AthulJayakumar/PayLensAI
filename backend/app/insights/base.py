"""Detector interface and shared structured-output helpers."""

from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from collections.abc import Sequence
from decimal import Decimal

from app.analytics.kpis import rate
from app.analytics.models import MoneyByCurrency
from app.insights.models import DetectionContext, Insight, InsightType
from app.insights.severity import classify_severity, detection_confidence


class Detector(ABC):
    """Contract implemented by every deterministic insight rule."""

    insight_type: InsightType

    @abstractmethod
    def detect(
        self, contexts: Sequence[DetectionContext], overall: DetectionContext
    ) -> list[Insight]:
        """Return deterministic structured insights."""


def relative_change(current: Decimal, baseline: Decimal) -> Decimal | None:
    """Return proportional change, or no result when baseline is zero."""

    if baseline == 0:
        return None
    return rate(current - baseline, baseline)


def currency_value(values: MoneyByCurrency, currency: str) -> MoneyByCurrency:
    """Return one requested currency without combining incompatible money."""

    return {currency: values.get(currency, Decimal("0"))}


def build_insight(
    *,
    insight_type: InsightType,
    segment: dict[str, str],
    metric: str,
    baseline_value: Decimal | None,
    current_value: Decimal,
    affected_values: MoneyByCurrency,
    transaction_count: int,
    affected_transaction_count: int,
    affected_attempted_value: MoneyByCurrency | None = None,
    affected_refund_amount: MoneyByCurrency | None = None,
    affected_dispute_amount: MoneyByCurrency | None = None,
    affected_payment_cost: MoneyByCurrency | None = None,
    evidence: dict[str, str | int | Decimal] | None = None,
) -> Insight:
    """Create one validated insight with consistent severity and confidence."""

    change = relative_change(current_value, baseline_value) if baseline_value is not None else None
    absolute = current_value - baseline_value if baseline_value is not None else None
    identity = json.dumps(
        {"type": insight_type.value, "segment": segment, "metric": metric}, sort_keys=True
    )
    insight_id = "ins_" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]
    return Insight(
        id=insight_id,
        type=insight_type,
        severity=classify_severity(
            relative_change=change,
            current_rate=current_value,
            affected_values=affected_values,
            sample_size=transaction_count,
        ),
        segment=segment,
        metric=metric,
        baseline_value=baseline_value,
        current_value=current_value,
        absolute_difference=absolute,
        relative_change=change,
        affected_attempted_value=affected_attempted_value or {},
        affected_refund_amount=affected_refund_amount or {},
        affected_dispute_amount=affected_dispute_amount or {},
        affected_payment_cost=affected_payment_cost or {},
        transaction_count=transaction_count,
        affected_transaction_count=affected_transaction_count,
        confidence=detection_confidence(transaction_count, change),
        evidence=evidence or {},
    )

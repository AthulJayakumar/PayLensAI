"""Deterministic severity and confidence classification."""

from __future__ import annotations

from decimal import Decimal

from app.analytics.models import MoneyByCurrency
from app.insights.models import Severity


def largest_currency_value(values: MoneyByCurrency) -> Decimal:
    """Return the largest same-currency exposure without cross-currency addition."""

    return max(values.values(), default=Decimal("0"))


def classify_severity(
    *,
    relative_change: Decimal | None,
    current_rate: Decimal,
    affected_values: MoneyByCurrency,
    sample_size: int,
) -> Severity:
    """Classify severity from magnitude, value exposure, and sample size.

    Cross-currency amounts are not added. The largest currency-specific exposure
    is used as a conservative deterministic signal until FX conversion exists.
    """

    if sample_size < 100:
        return Severity.LOW

    score = 0
    magnitude = abs(relative_change or Decimal("0"))
    if magnitude >= Decimal("2"):
        score += 3
    elif magnitude >= Decimal("1"):
        score += 2
    elif magnitude >= Decimal("0.5"):
        score += 1

    if current_rate >= Decimal("0.15"):
        score += 2
    elif current_rate >= Decimal("0.08"):
        score += 1

    affected_value = largest_currency_value(affected_values)
    if affected_value >= Decimal("10000"):
        score += 2
    elif affected_value >= Decimal("1000"):
        score += 1

    if sample_size >= 1000:
        score += 2
    elif sample_size >= 250:
        score += 1

    if score >= 7:
        return Severity.CRITICAL
    if score >= 5:
        return Severity.HIGH
    if score >= 3:
        return Severity.MEDIUM
    return Severity.LOW


def detection_confidence(sample_size: int, relative_change: Decimal | None) -> Decimal:
    """Return a bounded reproducible evidence score, not a statistical p-value."""

    sample_component = min(Decimal(sample_size) / Decimal("5000"), Decimal("0.35"))
    change_component = min(abs(relative_change or Decimal("0")) / Decimal("5"), Decimal("0.25"))
    return min(Decimal("0.99"), Decimal("0.40") + sample_component + change_component).quantize(
        Decimal("0.000001")
    )


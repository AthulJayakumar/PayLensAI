"""Period-over-period failure comparisons."""

from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal

from app.analytics.kpis import calculate_kpis, rate
from app.analytics.models import BaselineComparison
from app.models import PayLensTransaction


def compare_failure_periods(
    baseline_transactions: Iterable[PayLensTransaction],
    current_transactions: Iterable[PayLensTransaction],
    *,
    segment: dict[str, str] | None = None,
) -> BaselineComparison:
    """Compare failure performance using transaction-count denominators."""

    # Reusing the KPI engine guarantees comparison rates use the documented denominators.
    baseline = calculate_kpis(baseline_transactions)
    current = calculate_kpis(current_transactions)
    absolute_difference = current.failure_rate - baseline.failure_rate
    # Relative change is undefined when the baseline is zero; absolute difference still works.
    relative_change = (
        rate(absolute_difference, baseline.failure_rate)
        if baseline.failure_rate != 0
        else None
    )
    return BaselineComparison(
        segment=segment or {},
        baseline_failure_rate=baseline.failure_rate,
        current_failure_rate=current.failure_rate,
        absolute_difference=absolute_difference,
        relative_percentage_change=relative_change,
        affected_attempted_payment_value=current.failed_attempted_payment_value,
        transaction_count=current.transaction_count,
        failed_transaction_count=current.failed_transaction_count,
        baseline_transaction_count=baseline.transaction_count,
        baseline_failed_transaction_count=baseline.failed_transaction_count,
    )

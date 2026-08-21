"""Single- and multi-dimensional segmentation analytics."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence

from app.analytics.kpis import calculate_kpis
from app.analytics.models import SegmentDimension, SegmentMetrics, TimeGranularity
from app.models import PayLensTransaction


MISSING_SEGMENT_VALUE = "NOT_AVAILABLE"


def _time_key(transaction: PayLensTransaction, granularity: TimeGranularity) -> str:
    timestamp = transaction.transaction_created_at
    if granularity == TimeGranularity.DAY:
        return timestamp.strftime("%Y-%m-%d")
    if granularity == TimeGranularity.WEEK:
        return timestamp.strftime("%G-W%V")
    return timestamp.strftime("%Y-%m")


def segment_value(
    transaction: PayLensTransaction,
    dimension: SegmentDimension,
    time_granularity: TimeGranularity,
) -> str:
    if dimension == SegmentDimension.TIME_PERIOD:
        return _time_key(transaction, time_granularity)
    value = getattr(transaction, dimension.value)
    if value is None:
        return MISSING_SEGMENT_VALUE
    return value.value if hasattr(value, "value") else str(value)


def segment_metrics(
    transactions: Iterable[PayLensTransaction],
    dimensions: Sequence[SegmentDimension],
    *,
    time_granularity: TimeGranularity = TimeGranularity.MONTH,
) -> list[SegmentMetrics]:
    """Group transactions by any supported dimension combination."""

    if not dimensions:
        raise ValueError("at least one segment dimension is required")
    if len(set(dimensions)) != len(dimensions):
        raise ValueError("segment dimensions must be unique")

    groups: defaultdict[tuple[str, ...], list[PayLensTransaction]] = defaultdict(list)
    for transaction in transactions:
        key = tuple(segment_value(transaction, dimension, time_granularity) for dimension in dimensions)
        groups[key].append(transaction)

    results = []
    for key in sorted(groups):
        segment = {dimension.value: value for dimension, value in zip(dimensions, key, strict=True)}
        results.append(SegmentMetrics(segment=segment, metrics=calculate_kpis(groups[key])))
    return results


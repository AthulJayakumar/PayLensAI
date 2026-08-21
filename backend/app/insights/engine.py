"""Orchestration for period splitting, segmentation, and modular detection."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import datetime

from app.analytics.kpis import calculate_kpis
from app.analytics.models import SegmentDimension
from app.analytics.segmentation import segment_metrics
from app.insights.base import Detector
from app.insights.detectors import BUILT_IN_DETECTORS
from app.insights.models import DetectionContext, Insight
from app.models import PayLensTransaction


DEFAULT_SEGMENT_COMBINATIONS: tuple[tuple[SegmentDimension, ...], ...] = (
    (SegmentDimension.PROVIDER,),
    (SegmentDimension.PAYMENT_METHOD,),
    (SegmentDimension.CARD_NETWORK,),
    (SegmentDimension.ISSUER_COUNTRY,),
    (SegmentDimension.CURRENCY,),
    (SegmentDimension.CARD_NETWORK, SegmentDimension.ISSUER_COUNTRY),
    (SegmentDimension.PROVIDER, SegmentDimension.CARD_NETWORK),
    (SegmentDimension.PROVIDER, SegmentDimension.ISSUER_COUNTRY),
    (
        SegmentDimension.PROVIDER,
        SegmentDimension.ISSUER_COUNTRY,
        SegmentDimension.CARD_NETWORK,
    ),
)


class InsightEngine:
    def __init__(
        self,
        detectors: Sequence[Detector] | None = None,
        segment_combinations: Sequence[Sequence[SegmentDimension]] = DEFAULT_SEGMENT_COMBINATIONS,
    ) -> None:
        self.detectors = list(detectors) if detectors is not None else [item() for item in BUILT_IN_DETECTORS]
        self.segment_combinations = [tuple(item) for item in segment_combinations]

    def analyse(
        self,
        transactions: Iterable[PayLensTransaction],
        *,
        current_start: datetime,
        current_end: datetime | None = None,
    ) -> list[Insight]:
        """Discover insights using all history before ``current_start`` as baseline."""

        records = list(transactions)
        baseline_records = [item for item in records if item.transaction_created_at < current_start]
        current_records = [
            item
            for item in records
            if item.transaction_created_at >= current_start
            and (current_end is None or item.transaction_created_at < current_end)
        ]
        overall = DetectionContext(
            segment={},
            baseline=calculate_kpis(baseline_records),
            current=calculate_kpis(current_records),
        )
        contexts = self._segment_contexts(baseline_records, current_records)
        insights = [
            insight
            for detector in self.detectors
            for insight in detector.detect(contexts, overall)
        ]
        insights = self._suppress_redundant_localisations(insights)
        return sorted(
            insights,
            key=lambda item: (item.type.value, tuple(sorted(item.segment.items())), item.id),
        )

    def _segment_contexts(
        self,
        baseline_records: list[PayLensTransaction],
        current_records: list[PayLensTransaction],
    ) -> list[DetectionContext]:
        contexts: list[DetectionContext] = []
        for dimensions in self.segment_combinations:
            baseline = {
                tuple(sorted(item.segment.items())): item
                for item in segment_metrics(baseline_records, dimensions)
            }
            current = {
                tuple(sorted(item.segment.items())): item
                for item in segment_metrics(current_records, dimensions)
            }
            for key in sorted(set(baseline) | set(current)):
                baseline_metrics = (
                    baseline[key].metrics if key in baseline else calculate_kpis([])
                )
                current_metrics = current[key].metrics if key in current else calculate_kpis([])
                contexts.append(
                    DetectionContext(
                        segment=dict(key), baseline=baseline_metrics, current=current_metrics
                    )
                )
        return contexts

    @staticmethod
    def _suppress_redundant_localisations(insights: list[Insight]) -> list[Insight]:
        """Suppress child failure slices already explained by a root segment."""

        failure_types = {"FAILURE_SPIKE", "HIGH_FAILURE_SEGMENT"}
        roots: dict[str, set[tuple[str, str]]] = {}
        for insight in insights:
            if insight.type.value not in failure_types or len(insight.segment) != 1:
                continue
            roots.setdefault(insight.type.value, set()).add(next(iter(insight.segment.items())))

        filtered = []
        for insight in insights:
            if insight.type.value not in failure_types or len(insight.segment) == 1:
                filtered.append(insight)
                continue
            root_segments = roots.get(insight.type.value, set())
            explained = any(item in root_segments for item in insight.segment.items())
            if not explained:
                filtered.append(insight)
        return filtered

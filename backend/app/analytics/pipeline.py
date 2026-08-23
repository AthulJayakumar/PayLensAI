"""Measured end-to-end analytics pipeline for canonical CSV data."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from time import perf_counter

from pydantic import BaseModel, ConfigDict, Field

from app.analytics.csv_loader import load_transactions_csv
from app.analytics.kpis import calculate_kpis
from app.analytics.models import KPIMetrics
from app.insights.engine import InsightEngine
from app.insights.models import Insight


class ProcessingTimings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    data_loading_seconds: float = Field(ge=0)
    kpi_calculation_seconds: float = Field(ge=0)
    insight_detection_seconds: float = Field(ge=0)
    total_processing_seconds: float = Field(ge=0)


class AnalysisResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transaction_count: int = Field(ge=0)
    kpis: KPIMetrics
    insights: list[Insight]
    timings: ProcessingTimings


def analyse_csv(
    path: str | Path,
    *,
    current_start: datetime,
    current_end: datetime | None = None,
    insight_engine: InsightEngine | None = None,
) -> AnalysisResult:
    """Load, calculate overall KPIs, and discover structured insights."""

    # Separate monotonic timers expose loading, KPI, detector, and end-to-end costs.
    total_started = perf_counter()
    load_started = perf_counter()
    # Validation and canonical model construction happen at the input boundary.
    transactions = load_transactions_csv(path)
    load_finished = perf_counter()

    kpi_started = perf_counter()
    kpis = calculate_kpis(transactions)
    kpi_finished = perf_counter()

    insight_started = perf_counter()
    # Callers may inject a detector configuration; production uses the deterministic defaults.
    insights = (insight_engine or InsightEngine()).analyse(
        transactions, current_start=current_start, current_end=current_end
    )
    insight_finished = perf_counter()

    return AnalysisResult(
        transaction_count=len(transactions),
        kpis=kpis,
        insights=insights,
        timings=ProcessingTimings(
            data_loading_seconds=load_finished - load_started,
            kpi_calculation_seconds=kpi_finished - kpi_started,
            insight_detection_seconds=insight_finished - insight_started,
            total_processing_seconds=insight_finished - total_started,
        ),
    )

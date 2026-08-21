"""Replaceable persistence boundary for local analyses."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from threading import RLock

from pydantic import BaseModel, ConfigDict

from app.analytics.pipeline import AnalysisResult
from app.models import PayLensTransaction


class AnalysisPerformance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    upload_seconds: float
    validation_seconds: float
    kpi_seconds: float
    insight_seconds: float
    total_request_seconds: float


class AnalysisRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    analysis_id: str
    filename: str
    file_size: int
    created_at: datetime
    current_start: datetime
    current_end: datetime
    transactions: list[PayLensTransaction]
    result: AnalysisResult
    performance: AnalysisPerformance


class AnalysisRepository(ABC):
    @abstractmethod
    def save(self, analysis: AnalysisRecord) -> None:
        """Persist or replace an analysis record."""

    @abstractmethod
    def get(self, analysis_id: str) -> AnalysisRecord | None:
        """Retrieve an analysis by opaque identifier."""


class InMemoryAnalysisRepository(AnalysisRepository):
    """Thread-safe local prototype store; replaceable with PostgreSQL later."""

    def __init__(self) -> None:
        self._records: dict[str, AnalysisRecord] = {}
        self._lock = RLock()

    def save(self, analysis: AnalysisRecord) -> None:
        with self._lock:
            self._records[analysis.analysis_id] = analysis

    def get(self, analysis_id: str) -> AnalysisRecord | None:
        with self._lock:
            return self._records.get(analysis_id)


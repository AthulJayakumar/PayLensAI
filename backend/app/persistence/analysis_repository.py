"""PostgreSQL implementation of the existing AnalysisRepository boundary."""

from __future__ import annotations

import hashlib
import os
from collections import OrderedDict
from datetime import datetime, timezone
from threading import RLock
from time import monotonic

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.analytics.kpis import calculate_kpis
from app.analytics.pipeline import AnalysisResult, ProcessingTimings
from app.api.repositories import AnalysisRecord, AnalysisRepository
from app.insights.models import Insight
from app.models import PayLensTransaction
from app.persistence.database import (
    AnalysisInsightRow,
    AnalysisRow,
    CanonicalTransactionRow,
    MerchantRow,
    utcnow,
)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


class PostgreSQLAnalysisRepository(AnalysisRepository):
    """Persist analyses while keeping the API's repository contract unchanged."""
    """Transactional repository; JSONB preserves canonical inputs and insights."""

    def __init__(self, engine, *, cache_ttl_seconds: float | None = None, cache_max_entries: int | None = None) -> None:
        self.engine = engine
        # A short, bounded cache avoids repeating PostgreSQL transfer, Pydantic
        # validation, and KPI reconstruction every time a user reopens a page.
        self.cache_ttl_seconds = max(
            0.0,
            cache_ttl_seconds if cache_ttl_seconds is not None
            else float(os.environ.get("PAYLENS_ANALYSIS_CACHE_TTL_SECONDS", "60")),
        )
        self.cache_max_entries = max(
            0,
            cache_max_entries if cache_max_entries is not None
            else int(os.environ.get("PAYLENS_ANALYSIS_CACHE_MAX_ENTRIES", "1")),
        )
        self._cache: OrderedDict[str, tuple[float, AnalysisRecord]] = OrderedDict()
        self._cache_lock = RLock()

    def _cached(self, analysis_id: str) -> AnalysisRecord | None:
        """Return a fresh cached record, removing it when its TTL has elapsed."""
        if self.cache_ttl_seconds == 0 or self.cache_max_entries == 0:
            return None
        with self._cache_lock:
            cached = self._cache.get(analysis_id)
            if cached is None:
                return None
            cached_at, record = cached
            if monotonic() - cached_at >= self.cache_ttl_seconds:
                self._cache.pop(analysis_id, None)
                return None
            self._cache.move_to_end(analysis_id)
            return record

    def _remember(self, record: AnalysisRecord) -> None:
        """Store one immutable analysis reference and enforce the memory bound."""
        if self.cache_ttl_seconds == 0 or self.cache_max_entries == 0:
            return
        with self._cache_lock:
            self._cache[record.analysis_id] = (monotonic(), record)
            self._cache.move_to_end(record.analysis_id)
            while len(self._cache) > self.cache_max_entries:
                self._cache.popitem(last=False)

    def ensure_merchant(self, merchant_id: str, name: str) -> None:
        with Session(self.engine) as session, session.begin():
            row = session.get(MerchantRow, merchant_id)
            if row is None:
                session.add(MerchantRow(id=merchant_id, name=name))
            elif row.name != name:
                row.name = name

    def save(self, analysis: AnalysisRecord) -> None:
        """Atomically replace insight rows and upsert canonical transactions."""
        self.ensure_merchant(analysis.merchant_id, analysis.merchant_id)
        with Session(self.engine) as session, session.begin():
            row = session.get(AnalysisRow, analysis.analysis_id)
            values = {
                "merchant_id": analysis.merchant_id,
                "status": analysis.status,
                "source": analysis.source,
                "filename": analysis.filename,
                "file_size": analysis.file_size,
                "created_at": analysis.created_at,
                "current_start": analysis.current_start,
                "current_end": analysis.current_end,
                "performance": analysis.performance.model_dump(mode="json"),
                "timings": analysis.result.timings.model_dump(mode="json"),
                "metadata_json": {"transaction_count": analysis.result.transaction_count},
            }
            if row is None:
                row = AnalysisRow(id=analysis.analysis_id, **values)
                session.add(row)
            else:
                for key, value in values.items():
                    setattr(row, key, value)

            session.execute(delete(AnalysisInsightRow).where(AnalysisInsightRow.analysis_id == analysis.analysis_id))
            for insight in analysis.result.insights:
                session.add(AnalysisInsightRow(
                    insight_id=insight.id,
                    analysis_id=analysis.analysis_id,
                    merchant_id=analysis.merchant_id,
                    payload=insight.model_dump(mode="json"),
                ))

            # Provider identity, not analysis ID, defines canonical uniqueness.
            for transaction in analysis.transactions:
                existing = session.scalar(select(CanonicalTransactionRow).where(
                    CanonicalTransactionRow.merchant_id == analysis.merchant_id,
                    CanonicalTransactionRow.provider == transaction.provider.value,
                    CanonicalTransactionRow.provider_transaction_id == transaction.provider_transaction_id,
                ))
                payload = transaction.model_copy(update={"merchant_id": analysis.merchant_id}).model_dump(mode="json")
                if existing is None:
                    session.add(CanonicalTransactionRow(
                        id="ctx_" + hashlib.sha256(f"{analysis.merchant_id}:{transaction.id}".encode()).hexdigest()[:40],
                        merchant_id=analysis.merchant_id,
                        analysis_id=analysis.analysis_id,
                        provider=transaction.provider.value,
                        provider_transaction_id=transaction.provider_transaction_id,
                        provider_updated_at=transaction.updated_at_internal,
                        payload=payload,
                    ))
                else:
                    existing.analysis_id = analysis.analysis_id
                    existing.payload = payload
                    existing.provider_updated_at = transaction.updated_at_internal
                    existing.updated_at = utcnow()
        # In single-process/local mode the just-created record can be served
        # immediately. Deployed API processes independently refresh after TTL.
        self._remember(analysis)

    def _load_record(self, analysis_id: str) -> AnalysisRecord | None:
        """Rehydrate validated domain models from PostgreSQL."""
        with Session(self.engine) as session:
            row = session.get(AnalysisRow, analysis_id)
            if row is None:
                return None
            transaction_rows = session.scalars(
                select(CanonicalTransactionRow).where(CanonicalTransactionRow.analysis_id == analysis_id)
            ).all()
            insight_rows = session.scalars(
                select(AnalysisInsightRow).where(AnalysisInsightRow.analysis_id == analysis_id)
            ).all()
            transactions = [PayLensTransaction.model_validate(item.payload) for item in transaction_rows]
            insights = [Insight.model_validate(item.payload) for item in insight_rows]
            timings = ProcessingTimings.model_validate(row.timings)
            return AnalysisRecord(
                analysis_id=row.id,
                merchant_id=row.merchant_id,
                status=row.status,
                source=row.source,
                filename=row.filename,
                file_size=row.file_size,
                created_at=_aware(row.created_at),
                current_start=_aware(row.current_start),
                current_end=_aware(row.current_end),
                transactions=transactions,
                result=AnalysisResult(
                    transaction_count=len(transactions),
                    kpis=calculate_kpis(transactions),
                    insights=insights,
                    timings=timings,
                ),
                performance=row.performance,
            )

    def get(self, analysis_id: str) -> AnalysisRecord | None:
        """Use a bounded hot cache before rebuilding a large analysis from SQL."""
        cached = self._cached(analysis_id)
        if cached is not None:
            return cached
        record = self._load_record(analysis_id)
        if record is not None:
            self._remember(record)
        return record

    def get_for_merchant(self, analysis_id: str, merchant_id: str) -> AnalysisRecord | None:
        cached = self._cached(analysis_id)
        if cached is not None:
            return cached if cached.merchant_id == merchant_id else None
        with Session(self.engine) as session:
            owned = session.scalar(select(AnalysisRow.id).where(
                AnalysisRow.id == analysis_id, AnalysisRow.merchant_id == merchant_id
            ))
        return self.get(analysis_id) if owned else None

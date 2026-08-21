"""PostgreSQL implementation of the existing AnalysisRepository boundary."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

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
    """Transactional repository; JSONB preserves canonical inputs and insights."""

    def __init__(self, engine) -> None:
        self.engine = engine

    def ensure_merchant(self, merchant_id: str, name: str) -> None:
        with Session(self.engine) as session, session.begin():
            row = session.get(MerchantRow, merchant_id)
            if row is None:
                session.add(MerchantRow(id=merchant_id, name=name))
            elif row.name != name:
                row.name = name

    def save(self, analysis: AnalysisRecord) -> None:
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

    def get(self, analysis_id: str) -> AnalysisRecord | None:
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

    def get_for_merchant(self, analysis_id: str, merchant_id: str) -> AnalysisRecord | None:
        with Session(self.engine) as session:
            owned = session.scalar(select(AnalysisRow.id).where(
                AnalysisRow.id == analysis_id, AnalysisRow.merchant_id == merchant_id
            ))
        return self.get(analysis_id) if owned else None

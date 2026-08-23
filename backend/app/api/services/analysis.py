"""CSV upload orchestration reusing the verified analytics engine."""

from __future__ import annotations

import csv
import secrets
import tempfile
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from time import perf_counter

from fastapi import UploadFile

from app.analytics.csv_loader import CSVTransactionValidationError, load_transactions_csv
from app.analytics.kpis import calculate_kpis
from app.analytics.pipeline import AnalysisResult, ProcessingTimings
from app.api.auth import AuthenticatedMerchant
from app.api.errors import APIError
from app.api.repositories import (
    AnalysisPerformance,
    AnalysisRecord,
    AnalysisRepository,
)
from app.insights.engine import InsightEngine
from app.persistence.pilot_repository import AuditEvent


DEFAULT_MAX_UPLOAD_BYTES = 64 * 1024 * 1024
UPLOAD_CHUNK_BYTES = 1024 * 1024


def _analysis_id() -> str:
    """Create an opaque, time-sortable public analysis identifier."""
    timestamp = int(datetime.now(timezone.utc).timestamp() * 1000)
    return f"analysis_{timestamp:013X}{secrets.token_hex(6).upper()}"


def _comparison_window(transactions) -> tuple[datetime, datetime]:
    """Use the final fifteen days as current and earlier rows as baseline."""
    latest = max(item.transaction_created_at for item in transactions)
    next_date = latest.date() + timedelta(days=1)
    current_end = datetime.combine(next_date, time.min, tzinfo=latest.tzinfo)
    return current_end - timedelta(days=15), current_end


class AnalysisService:
    """Validate uploads, run verified engines, persist results, and audit creation."""
    def __init__(
        self,
        repository: AnalysisRepository,
        *,
        max_upload_bytes: int = DEFAULT_MAX_UPLOAD_BYTES,
        insight_engine: InsightEngine | None = None,
        audit_store=None,
    ) -> None:
        self.repository = repository
        self.max_upload_bytes = max_upload_bytes
        self.insight_engine = insight_engine or InsightEngine()
        self.audit_store = audit_store

    def _audit_created(self, record: AnalysisRecord, merchant: AuthenticatedMerchant) -> None:
        if self.audit_store is not None:
            self.audit_store.record(AuditEvent(merchant_id=merchant.merchant_id, actor_id=merchant.actor_id,
                event_type="ANALYSIS_CREATED", resource=record.analysis_id,
                safe_metadata={"source": record.source, "transaction_count": record.result.transaction_count}))

    async def create_analysis(
        self, upload: UploadFile, merchant: AuthenticatedMerchant
    ) -> AnalysisRecord:
        """Stream an untrusted upload to disk before parsing and calculation."""
        request_started = perf_counter()
        filename = Path(upload.filename or "").name
        if not filename.lower().endswith(".csv"):
            raise APIError(
                status_code=415,
                code="UNSUPPORTED_FILE_TYPE",
                message="Upload a file with a .csv extension.",
            )
        # Extensions and MIME types are screened before canonical row validation.
        allowed_content_types = {
            "text/csv",
            "application/csv",
            "application/vnd.ms-excel",
            "text/plain",
            "application/octet-stream",
            "",
            None,
        }
        if upload.content_type not in allowed_content_types:
            raise APIError(
                status_code=415,
                code="UNSUPPORTED_FILE_TYPE",
                message="The uploaded file is not a supported CSV content type.",
            )

        upload_started = perf_counter()
        size = 0
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as temporary:
                temporary_path = Path(temporary.name)
                while chunk := await upload.read(UPLOAD_CHUNK_BYTES):
                    size += len(chunk)
                    if size > self.max_upload_bytes:
                        raise APIError(
                            status_code=413,
                            code="FILE_TOO_LARGE",
                            message=(
                                f"CSV files must not exceed {self.max_upload_bytes // (1024 * 1024)} MiB."
                            ),
                        )
                    temporary.write(chunk)
            upload_finished = perf_counter()
            if size == 0:
                raise APIError(
                    status_code=400,
                    code="EMPTY_FILE",
                    message="The uploaded CSV file is empty.",
                )

            validation_started = perf_counter()
            try:
                transactions = [
                    transaction.model_copy(update={"merchant_id": merchant.merchant_id})
                    for transaction in load_transactions_csv(temporary_path)
                ]
            except (CSVTransactionValidationError, csv.Error, UnicodeDecodeError) as error:
                raise APIError(
                    status_code=422,
                    code="INVALID_TRANSACTION_DATA",
                    message="The CSV does not contain valid canonical PayLens transactions.",
                    details=[str(error)],
                ) from error
            validation_finished = perf_counter()
            if not transactions:
                raise APIError(
                    status_code=422,
                    code="EMPTY_DATASET",
                    message="The CSV contains headers but no transactions.",
                )

            current_start, current_end = _comparison_window(transactions)
            kpi_started = perf_counter()
            kpis = calculate_kpis(transactions)
            kpi_finished = perf_counter()
            insight_started = perf_counter()
            insights = self.insight_engine.analyse(
                transactions, current_start=current_start, current_end=current_end
            )
            insight_finished = perf_counter()

            result = AnalysisResult(
                transaction_count=len(transactions),
                kpis=kpis,
                insights=insights,
                timings=ProcessingTimings(
                    data_loading_seconds=validation_finished - validation_started,
                    kpi_calculation_seconds=kpi_finished - kpi_started,
                    insight_detection_seconds=insight_finished - insight_started,
                    total_processing_seconds=insight_finished - validation_started,
                ),
            )
            record = AnalysisRecord(
                analysis_id=_analysis_id(),
                merchant_id=merchant.merchant_id,
                filename=filename,
                file_size=size,
                created_at=datetime.now(timezone.utc),
                current_start=current_start,
                current_end=current_end,
                transactions=transactions,
                result=result,
                performance=AnalysisPerformance(
                    upload_seconds=upload_finished - upload_started,
                    validation_seconds=validation_finished - validation_started,
                    kpi_seconds=kpi_finished - kpi_started,
                    insight_seconds=insight_finished - insight_started,
                    total_request_seconds=insight_finished - request_started,
                ),
            )
            self.repository.save(record)
            self._audit_created(record, merchant)
            return record
        finally:
            await upload.close()
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    def create_from_transactions(
        self,
        transactions,
        merchant: AuthenticatedMerchant,
        *,
        filename: str,
        source: str,
    ) -> AnalysisRecord:
        """Feed already-normalized provider rows through the same analytics path."""
        """Run the verified engine for provider-normalised canonical transactions."""
        started = perf_counter()
        transactions = [item.model_copy(update={"merchant_id": merchant.merchant_id}) for item in transactions]
        if not transactions:
            raise APIError(status_code=422, code="EMPTY_DATASET", message="No canonical provider transactions are available for analysis.")
        current_start, current_end = _comparison_window(transactions)
        kpi_started = perf_counter()
        kpis = calculate_kpis(transactions)
        kpi_finished = perf_counter()
        insight_started = perf_counter()
        insights = self.insight_engine.analyse(transactions, current_start=current_start, current_end=current_end)
        insight_finished = perf_counter()
        record = AnalysisRecord(
            analysis_id=_analysis_id(), merchant_id=merchant.merchant_id, status="COMPLETED", source=source,
            filename=filename, file_size=0, created_at=datetime.now(timezone.utc),
            current_start=current_start, current_end=current_end, transactions=transactions,
            result=AnalysisResult(
                transaction_count=len(transactions), kpis=kpis, insights=insights,
                timings=ProcessingTimings(
                    data_loading_seconds=0,
                    kpi_calculation_seconds=kpi_finished - kpi_started,
                    insight_detection_seconds=insight_finished - insight_started,
                    total_processing_seconds=insight_finished - started,
                ),
            ),
            performance=AnalysisPerformance(
                upload_seconds=0, validation_seconds=0,
                kpi_seconds=kpi_finished - kpi_started,
                insight_seconds=insight_finished - insight_started,
                total_request_seconds=insight_finished - started,
            ),
        )
        self.repository.save(record)
        self._audit_created(record, merchant)
        return record

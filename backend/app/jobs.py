"""SQS-backed job dispatch and deterministic worker execution."""

from __future__ import annotations

import json
import secrets
import asyncio
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from fastapi import UploadFile

from app.api.auth import AuthenticatedMerchant
from app.providers.models import AsyncJob, JobStatus, JobType


class InMemoryJobQueue:
    """Deterministic queue double used by local tests."""
    def __init__(self) -> None:
        self.messages: list[dict] = []

    def send(self, queue: JobType, job_id: str) -> None:
        self.messages.append({"type": queue.value, "job_id": job_id})


class SQSJobQueue:
    """Send minimal job references while full payloads remain in PostgreSQL."""
    def __init__(self, queue_urls: dict[JobType, str], client=None) -> None:
        if client is None:
            import boto3
            client = boto3.client("sqs")
        self.client, self.queue_urls = client, queue_urls

    def send(self, queue: JobType, job_id: str) -> None:
        self.client.send_message(QueueUrl=self.queue_urls[queue], MessageBody=json.dumps({"type": queue.value, "job_id": job_id}))


class S3AnalysisUploadStore:
    """Stage large CSV inputs in encrypted S3 for asynchronous analysis."""
    def __init__(self, *, bucket: str, kms_key_id: str, client=None) -> None:
        if client is None:
            import boto3
            client = boto3.client("s3")
        self.client, self.bucket, self.kms_key_id = client, bucket, kms_key_id

    async def put(self, upload: UploadFile, merchant_id: str, upload_id: str, max_bytes: int) -> tuple[str, int, str]:
        """Stream with a size cap and return an opaque tenant-scoped key."""
        filename = Path(upload.filename or "transactions.csv").name
        if not filename.lower().endswith(".csv"):
            raise ValueError("Only CSV uploads are supported")
        key = f"analysis-input/{secrets.token_hex(8)}/{upload_id}.csv"
        size = 0
        with tempfile.TemporaryFile() as temporary:
            while chunk := await upload.read(1024 * 1024):
                size += len(chunk)
                if size > max_bytes:
                    raise ValueError("Upload exceeds configured limit")
                temporary.write(chunk)
            temporary.seek(0)
            self.client.upload_fileobj(temporary, self.bucket, key, ExtraArgs={"ServerSideEncryption": "aws:kms", "SSEKMSKeyId": self.kms_key_id,
                "ContentType": "text/csv", "Metadata": {"merchant-hash": __import__("hashlib").sha256(merchant_id.encode()).hexdigest()}})
        await upload.close()
        return key, size, filename

    def download(self, key: str, destination) -> None:
        self.client.download_fileobj(self.bucket, key, destination)

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)


class JobService:
    """Persist idempotent jobs before dispatching identifiers to a queue."""
    def __init__(self, repository, queue) -> None:
        self.repository, self.queue = repository, queue

    def enqueue(self, *, merchant_id: str, job_type: JobType, deduplication_key: str, payload: dict) -> AsyncJob:
        now = datetime.now(timezone.utc)
        job = AsyncJob(id=f"job_{secrets.token_hex(16)}", merchant_id=merchant_id, type=job_type,
                       deduplication_key=deduplication_key, payload=payload, created_at=now, updated_at=now)
        job, created = self.repository.create_job(job)
        if created:
            self.queue.send(job_type, job.id)
        return job

    def get_owned(self, job_id: str, merchant_id: str) -> AsyncJob | None:
        return self.repository.get_job(job_id, merchant_id)

    def recent(self, merchant_id: str, *, limit: int = 10) -> list[AsyncJob]:
        return self.repository.list_jobs(merchant_id, limit=limit)

    def retry(self, job_id: str, merchant_id: str) -> AsyncJob:
        """Create one idempotent manual retry for a failed merchant-owned job."""
        failed = self.get_owned(job_id, merchant_id)
        if failed is None:
            raise KeyError(job_id)
        if failed.status != JobStatus.FAILED:
            raise ValueError("Only failed jobs can be retried")
        return self.enqueue(
            merchant_id=merchant_id,
            job_type=failed.type,
            deduplication_key=f"manual-retry:{failed.id}",
            payload={**failed.payload, "retry_of": failed.id},
        )


class JobWorker:
    """Transition durable jobs and reuse existing provider/analysis services."""
    """Executes a persisted job using the existing provider/analysis services."""

    def __init__(self, repository, provider_service, *, analysis_service=None, upload_store=None) -> None:
        self.repository, self.provider_service = repository, provider_service
        self.analysis_service, self.upload_store = analysis_service, upload_store

    def execute(self, job_id: str, merchant_id: str) -> AsyncJob:
        """Run one job with explicit RUNNING/COMPLETED/FAILED persistence."""
        job = self.repository.get_job(job_id, merchant_id)
        if job is None:
            raise KeyError(job_id)
        if job.status == JobStatus.COMPLETED:
            return job
        job = job.model_copy(update={"status": JobStatus.RUNNING, "attempts": job.attempts + 1, "updated_at": datetime.now(timezone.utc)})
        self.repository.save_job(job)
        # These branches orchestrate existing services rather than duplicating
        # Stripe normalization or analytics logic inside the worker.
        try:
            if job.type == JobType.PROVIDER_SYNC:
                merchant = AuthenticatedMerchant(merchant_id=job.merchant_id, name="Queued merchant", actor_id=job.payload.get("actor_id"))
                sync = self.provider_service.sync(merchant, resume_job_id=job.payload.get("resume_job_id"))
                result = {
                    "sync_job_id": sync.id,
                    "analysis_id": sync.analysis_id,
                    "status": sync.status.value,
                    "records_received": sync.records_received,
                    "records_normalised": sync.records_normalised,
                    "transaction_count": sync.records_normalised,
                }
            elif job.type == JobType.WEBHOOK:
                result = self.provider_service.process_verified_webhook(job.payload["event"], already_recorded=True)
            elif job.type == JobType.ANALYSIS:
                if self.analysis_service is None or self.upload_store is None:
                    raise RuntimeError("Analysis worker storage is not configured")
                with tempfile.NamedTemporaryFile(suffix=".csv") as temporary:
                    self.upload_store.download(job.payload["s3_key"], temporary)
                    temporary.seek(0)
                    upload = UploadFile(temporary, filename=job.payload["filename"])
                    merchant = AuthenticatedMerchant(merchant_id=job.merchant_id, name="Queued merchant", actor_id=job.payload.get("actor_id"))
                    analysis = asyncio.run(self.analysis_service.create_analysis(upload, merchant))
                self.upload_store.delete(job.payload["s3_key"])
                result = {"analysis_id": analysis.analysis_id, "transaction_count": analysis.result.transaction_count}
            else:
                raise ValueError("Unsupported worker job type")
            job = job.model_copy(update={"status": JobStatus.COMPLETED, "result": result, "updated_at": datetime.now(timezone.utc)})
        except Exception as error:
            job = job.model_copy(update={"status": JobStatus.FAILED, "error_code": type(error).__name__, "updated_at": datetime.now(timezone.utc)})
            self.repository.save_job(job)
            raise
        self.repository.save_job(job)
        return job

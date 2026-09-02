"""Long-poll SQS and execute PayLens jobs; one process handles all pilot queues."""

from __future__ import annotations

import json
import logging
import os
import signal

import boto3

from app.api.main import create_app
from app.jobs import JobWorker
from app.providers.models import JobType

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"), format="%(message)s")
logger = logging.getLogger("paylens.worker")
running = True


def stop(*_args) -> None:
    """Ask the long-poll loop to finish cleanly after SIGTERM/SIGINT."""
    global running
    running = False


def main() -> None:
    """Poll every configured queue and delete messages only after success."""
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    app = create_app()
    store = app.state.analysis_upload_store
    worker = JobWorker(app.state.pilot_repository, app.state.provider_service,
                       analysis_service=app.state.analysis_service, upload_store=store)
    queues = {
        JobType.PROVIDER_SYNC: os.environ["PAYLENS_PROVIDER_SYNC_QUEUE_URL"],
        JobType.ANALYSIS: os.environ["PAYLENS_ANALYSIS_QUEUE_URL"],
        JobType.WEBHOOK: os.environ["PAYLENS_WEBHOOK_QUEUE_URL"],
    }
    sqs = boto3.client("sqs")
    # A single small-pilot process services all job types without duplicating code.
    while running:
        empty = True
        for queue_url in queues.values():
            # Keep each queue's configured visibility timeout. Overriding it here
            # would shorten 15-minute sync/analysis leases and allow duplicate work.
            response = sqs.receive_message(QueueUrl=queue_url, MaxNumberOfMessages=1, WaitTimeSeconds=5)
            for message in response.get("Messages", []):
                empty = False
                body = json.loads(message["Body"])
                try:
                    job = app.state.pilot_repository.get_job(body["job_id"], merchant_id=_merchant_for_job(app, body["job_id"]))
                    worker.execute(job.id, job.merchant_id)
                    sqs.delete_message(QueueUrl=queue_url, ReceiptHandle=message["ReceiptHandle"])
                    logger.info(json.dumps({"event": "job_completed", "job_id": job.id, "job_type": job.type.value}))
                except Exception as error:
                    logger.error(json.dumps({"event": "job_failed", "job_id": body.get("job_id"), "error_type": type(error).__name__}))
        if not running or not empty:
            continue


def _merchant_for_job(app, job_id: str) -> str:
    """Resolve trusted ownership from persistence, never from the SQS message."""
    repository = app.state.pilot_repository
    if hasattr(repository, "engine"):
        from sqlalchemy import select
        from sqlalchemy.orm import Session
        from app.persistence.database import AsyncJobRow
        with Session(repository.engine) as session:
            return session.scalar(select(AsyncJobRow.merchant_id).where(AsyncJobRow.id == job_id))
    return repository.jobs[job_id].merchant_id


if __name__ == "__main__":
    main()

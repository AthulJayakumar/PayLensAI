"""Stripe connection, synchronization, reconciliation, and disconnect routes."""

from __future__ import annotations

import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, ConfigDict

from app.api.auth import AuthenticatedMerchant, MerchantRole
from app.api.dependencies import get_current_merchant, get_provider_service, require_roles
from app.api.errors import APIError
from app.api.services.providers import ProviderService
from app.providers.models import JobType


router = APIRouter(prefix="/providers", tags=["providers"])


class SyncRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    resume_job_id: str | None = None


def connection_payload(connection) -> dict:
    """Expose connection metadata without returning encrypted credentials."""
    if connection is None:
        return {"provider": "STRIPE", "status": "NOT_CONNECTED", "configured": False}
    return connection.model_dump(mode="json")


@router.get("")
def provider_status(
    merchant: AuthenticatedMerchant = Depends(get_current_merchant),
    service: ProviderService = Depends(get_provider_service),
) -> dict:
    """Describe Stripe configuration and connection state for this merchant."""
    connection = service.status(merchant.merchant_id)
    return {"providers": [{
        **connection_payload(connection),
        "configured": service.connector is not None,
        "connection_mode": service.connector.connection_mode if service.connector is not None else None,
    }]}


@router.get("/stripe/diagnostics")
def stripe_diagnostics(
    http_request: Request,
    merchant: AuthenticatedMerchant = Depends(get_current_merchant),
    service: ProviderService = Depends(get_provider_service),
) -> dict:
    """Expose safe, tenant-scoped ingestion health for pilot operators."""
    diagnostics = service.diagnostics(merchant.merchant_id)
    jobs = getattr(http_request.app.state, "job_service", None)
    recent_jobs = jobs.recent(merchant.merchant_id, limit=10) if jobs is not None else []
    retried_job_ids = {job.payload.get("retry_of") for job in recent_jobs if job.payload.get("retry_of")}
    if any(job.status.value == "FAILED" and job.id not in retried_job_ids for job in recent_jobs):
        diagnostics["pipeline_status"] = "DEGRADED"
    diagnostics["recent_jobs"] = [
        {
            "id": job.id,
            "type": job.type.value,
            "status": job.status.value,
            "attempts": job.attempts,
            "error_code": job.error_code,
            "created_at": job.created_at,
            "updated_at": job.updated_at,
            "retryable": job.status.value == "FAILED" and job.id not in retried_job_ids,
        }
        for job in recent_jobs
    ]
    diagnostics["delivery_protection"] = {
        "automatic_attempts": 4,
        "dead_letter_queue": True,
    }
    return {"diagnostics": diagnostics}


@router.post("/stripe/authorize")
def authorize_stripe(
    merchant: AuthenticatedMerchant = Depends(require_roles(MerchantRole.OWNER, MerchantRole.ADMIN)),
    service: ProviderService = Depends(get_provider_service),
) -> dict:
    """Issue protected OAuth state and return Stripe's authorization URL."""
    return {"authorization_url": service.authorization_url(merchant.merchant_id)}


@router.post("/stripe/connect-sandbox")
def connect_stripe_sandbox(
    merchant: AuthenticatedMerchant = Depends(require_roles(MerchantRole.OWNER, MerchantRole.ADMIN)),
    service: ProviderService = Depends(get_provider_service),
) -> dict:
    """Bind the configured private Stripe sandbox to the pilot merchant."""
    connection = service.connect_sandbox(merchant.merchant_id, actor_id=merchant.actor_id)
    return {"connection": {**connection.model_dump(mode="json"), "configured": True, "connection_mode": "SANDBOX_KEY"}}


@router.get("/stripe/oauth/callback")
def stripe_oauth_callback(
    code: str = Query(..., min_length=1, max_length=500),
    state: str = Query(..., min_length=32, max_length=2048),
    service: ProviderService = Depends(get_provider_service),
) -> RedirectResponse:
    """Consume the one-time callback and redirect to the provider screen."""
    service.complete_authorization(code=code, state=state)
    frontend_url = os.environ.get("PAYLENS_FRONTEND_URL", "http://localhost:3000").rstrip("/")
    return RedirectResponse(f"{frontend_url}/providers?stripe=connected", status_code=303)


@router.post("/stripe/sync", status_code=status.HTTP_202_ACCEPTED)
def sync_stripe(
    http_request: Request,
    request: SyncRequest | None = None,
    merchant: AuthenticatedMerchant = Depends(require_roles(MerchantRole.OWNER, MerchantRole.ADMIN, MerchantRole.ANALYST)),
    service: ProviderService = Depends(get_provider_service),
) -> dict:
    """Queue a durable sync on AWS or execute it synchronously locally."""
    jobs = getattr(http_request.app.state, "job_service", None)
    if jobs is not None:
        connection = service.status(merchant.merchant_id)
        if connection is None:
            raise APIError(status_code=409, code="STRIPE_NOT_CONNECTED", message="Connect Stripe before starting a sync.")
        dedupe_suffix = request.resume_job_id if request and request.resume_job_id else datetime.now(timezone.utc).strftime("%Y%m%d%H")
        job = jobs.enqueue(merchant_id=merchant.merchant_id, job_type=JobType.PROVIDER_SYNC,
                           deduplication_key=f"provider-sync:{connection.id}:{dedupe_suffix}",
                           payload={"resume_job_id": request.resume_job_id if request else None, "actor_id": merchant.actor_id})
        return {"job": job.model_dump(mode="json")}
    job = service.sync(merchant, resume_job_id=request.resume_job_id if request else None)
    return {"sync_job": job.model_dump(mode="json")}


@router.get("/stripe/sync/{job_id}")
def get_sync_job(
    job_id: str,
    merchant: AuthenticatedMerchant = Depends(get_current_merchant),
    service: ProviderService = Depends(get_provider_service),
) -> dict:
    """Return a provider sync job only when the merchant owns it."""
    job = service.repository.get_sync_job(job_id, merchant.merchant_id)
    if job is None:
        raise APIError(status_code=404, code="SYNC_JOB_NOT_FOUND", message="The sync job does not exist for this merchant.")
    return {"sync_job": job.model_dump(mode="json")}


@router.post("/stripe/reconcile")
def reconcile_stripe(
    merchant: AuthenticatedMerchant = Depends(require_roles(MerchantRole.OWNER, MerchantRole.ADMIN)),
    service: ProviderService = Depends(get_provider_service),
) -> dict:
    """Detect and repair drift between Stripe and canonical transactions."""
    return {"reconciliation": service.reconcile(merchant.merchant_id).model_dump()}


@router.delete("/stripe", status_code=status.HTTP_204_NO_CONTENT)
def disconnect_stripe(
    merchant: AuthenticatedMerchant = Depends(require_roles(MerchantRole.OWNER, MerchantRole.ADMIN)),
    service: ProviderService = Depends(get_provider_service),
) -> None:
    """Attempt provider revocation, remove local credentials, and audit it."""
    service.disconnect(merchant.merchant_id, actor_id=merchant.actor_id)

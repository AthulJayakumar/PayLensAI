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
    if connection is None:
        return {"provider": "STRIPE", "status": "NOT_CONNECTED", "configured": False}
    return connection.model_dump(mode="json")


@router.get("")
def provider_status(
    merchant: AuthenticatedMerchant = Depends(get_current_merchant),
    service: ProviderService = Depends(get_provider_service),
) -> dict:
    connection = service.status(merchant.merchant_id)
    return {"providers": [{**connection_payload(connection), "configured": service.connector is not None}]}


@router.post("/stripe/authorize")
def authorize_stripe(
    merchant: AuthenticatedMerchant = Depends(require_roles(MerchantRole.OWNER, MerchantRole.ADMIN)),
    service: ProviderService = Depends(get_provider_service),
) -> dict:
    return {"authorization_url": service.authorization_url(merchant.merchant_id)}


@router.get("/stripe/oauth/callback")
def stripe_oauth_callback(
    code: str = Query(..., min_length=1, max_length=500),
    state: str = Query(..., min_length=32, max_length=2048),
    service: ProviderService = Depends(get_provider_service),
) -> RedirectResponse:
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
    job = service.repository.get_sync_job(job_id, merchant.merchant_id)
    if job is None:
        raise APIError(status_code=404, code="SYNC_JOB_NOT_FOUND", message="The sync job does not exist for this merchant.")
    return {"sync_job": job.model_dump(mode="json")}


@router.post("/stripe/reconcile")
def reconcile_stripe(
    merchant: AuthenticatedMerchant = Depends(require_roles(MerchantRole.OWNER, MerchantRole.ADMIN)),
    service: ProviderService = Depends(get_provider_service),
) -> dict:
    return {"reconciliation": service.reconcile(merchant.merchant_id).model_dump()}


@router.delete("/stripe", status_code=status.HTTP_204_NO_CONTENT)
def disconnect_stripe(
    merchant: AuthenticatedMerchant = Depends(require_roles(MerchantRole.OWNER, MerchantRole.ADMIN)),
    service: ProviderService = Depends(get_provider_service),
) -> None:
    service.disconnect(merchant.merchant_id, actor_id=merchant.actor_id)

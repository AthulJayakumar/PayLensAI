"""Read-only API for polling asynchronous job state."""

from fastapi import APIRouter, Depends, Request, status

from app.api.auth import AuthenticatedMerchant, MerchantRole
from app.api.dependencies import get_current_merchant, require_roles
from app.api.errors import APIError

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("/{job_id}")
def job_status(job_id: str, request: Request, merchant: AuthenticatedMerchant = Depends(get_current_merchant)) -> dict:
    """Return a job only when it belongs to the authenticated merchant."""
    service = getattr(request.app.state, "job_service", None)
    job = service.get_owned(job_id, merchant.merchant_id) if service else None
    if job is None:
        raise APIError(status_code=404, code="JOB_NOT_FOUND", message="The job does not exist for this merchant.")
    return {"job": job.model_dump(mode="json")}


@router.post("/{job_id}/retry", status_code=status.HTTP_202_ACCEPTED)
def retry_job(
    job_id: str,
    request: Request,
    merchant: AuthenticatedMerchant = Depends(require_roles(MerchantRole.OWNER, MerchantRole.ADMIN)),
) -> dict:
    """Queue one merchant-scoped manual retry without exposing stored job payloads."""
    service = getattr(request.app.state, "job_service", None)
    if service is None:
        raise APIError(status_code=409, code="ASYNC_JOBS_DISABLED", message="Job retries are unavailable in synchronous mode.")
    try:
        job = service.retry(job_id, merchant.merchant_id)
    except KeyError as error:
        raise APIError(status_code=404, code="JOB_NOT_FOUND", message="The job does not exist for this merchant.") from error
    except ValueError as error:
        raise APIError(status_code=409, code="JOB_NOT_RETRYABLE", message="Only failed jobs can be retried.") from error
    return {"job": job.model_dump(mode="json")}

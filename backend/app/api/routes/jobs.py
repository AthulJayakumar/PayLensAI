from fastapi import APIRouter, Depends, Request

from app.api.auth import AuthenticatedMerchant
from app.api.dependencies import get_current_merchant
from app.api.errors import APIError

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("/{job_id}")
def job_status(job_id: str, request: Request, merchant: AuthenticatedMerchant = Depends(get_current_merchant)) -> dict:
    service = getattr(request.app.state, "job_service", None)
    job = service.get_owned(job_id, merchant.merchant_id) if service else None
    if job is None:
        raise APIError(status_code=404, code="JOB_NOT_FOUND", message="The job does not exist for this merchant.")
    return {"job": job.model_dump(mode="json")}

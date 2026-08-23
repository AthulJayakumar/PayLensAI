"""Create and retrieve merchant-owned CSV analyses."""

import secrets
from fastapi import APIRouter, Depends, File, Request, Response, UploadFile, status

from app.api.auth import AuthenticatedMerchant, MerchantRole
from app.api.dependencies import get_analysis_service, require_analysis, require_roles
from app.api.repositories import AnalysisRecord
from app.api.services.analysis import AnalysisService
from app.providers.models import JobType


router = APIRouter(prefix="/analysis", tags=["analysis"])


def analysis_summary(record: AnalysisRecord) -> dict:
    """Serialize the stable summary shared by upload and retrieval responses."""
    return {
        "analysis_id": record.analysis_id,
        "status": "COMPLETED",
        "filename": record.filename,
        "file_size": record.file_size,
        "created_at": record.created_at.isoformat(),
        "transaction_count": record.result.transaction_count,
        "insight_count": len(record.result.insights),
        "currencies": sorted(record.result.kpis.attempted_payment_value),
        "comparison_period": {
            "current_start": record.current_start.isoformat(),
            "current_end": record.current_end.isoformat(),
            "baseline": "all transactions before current_start",
        },
        "performance": record.performance.model_dump(),
    }


@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_analysis(
    request: Request,
    response: Response,
    file: UploadFile = File(...),
    service: AnalysisService = Depends(get_analysis_service),
    merchant: AuthenticatedMerchant = Depends(require_roles(MerchantRole.OWNER, MerchantRole.ADMIN, MerchantRole.ANALYST)),
) -> dict:
    """Analyse immediately locally or enqueue an S3-backed AWS job."""
    jobs = getattr(request.app.state, "job_service", None)
    upload_store = getattr(request.app.state, "analysis_upload_store", None)
    # AWS stores the large body in S3 and sends only a durable reference to SQS.
    if jobs is not None and upload_store is not None:
        upload_id = f"upload_{secrets.token_hex(12)}"
        try:
            s3_key, size, filename = await upload_store.put(file, merchant.merchant_id, upload_id, service.max_upload_bytes)
        except ValueError as error:
            from app.api.errors import APIError
            raise APIError(status_code=413 if "limit" in str(error) else 415, code="INVALID_UPLOAD", message=str(error)) from error
        job = jobs.enqueue(merchant_id=merchant.merchant_id, job_type=JobType.ANALYSIS,
                           deduplication_key=f"analysis:{upload_id}",
                           payload={"s3_key": s3_key, "filename": filename, "file_size": size, "actor_id": merchant.actor_id})
        response.status_code = status.HTTP_202_ACCEPTED
        return {"job": job.model_dump(mode="json")}
    record = await service.create_analysis(file, merchant)
    return analysis_summary(record)


@router.get("/{analysis_id}")
def get_analysis(record: AnalysisRecord = Depends(require_analysis)) -> dict:
    """Return an analysis after merchant ownership has been enforced."""
    return analysis_summary(record)

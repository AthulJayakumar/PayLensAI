from fastapi import APIRouter, Depends, File, UploadFile, status

from app.api.dependencies import get_analysis_service, require_analysis
from app.api.repositories import AnalysisRecord
from app.api.services.analysis import AnalysisService


router = APIRouter(prefix="/analysis", tags=["analysis"])


def analysis_summary(record: AnalysisRecord) -> dict:
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
    file: UploadFile = File(...),
    service: AnalysisService = Depends(get_analysis_service),
) -> dict:
    record = await service.create_analysis(file)
    return analysis_summary(record)


@router.get("/{analysis_id}")
def get_analysis(record: AnalysisRecord = Depends(require_analysis)) -> dict:
    return analysis_summary(record)


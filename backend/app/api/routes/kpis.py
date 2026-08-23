"""HTTP projection of the KPI result stored for an analysis."""

from fastapi import APIRouter, Depends

from app.api.dependencies import require_analysis
from app.api.repositories import AnalysisRecord
from app.api.serialization import metrics_payload


router = APIRouter(prefix="/analysis", tags=["kpis"])


@router.get("/{analysis_id}/kpis")
def get_kpis(record: AnalysisRecord = Depends(require_analysis)) -> dict:
    """Serialize aggregate metrics for a merchant-owned analysis."""
    return {"analysis_id": record.analysis_id, **metrics_payload(record.result.kpis)}

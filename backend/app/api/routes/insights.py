from fastapi import APIRouter, Depends, Query

from app.api.dependencies import get_explanation_provider, require_analysis
from app.api.errors import APIError
from app.api.explanations import ExplanationProvider
from app.api.repositories import AnalysisRecord
from app.api.serialization import insight_payload
from app.insights.models import InsightType, Severity


router = APIRouter(prefix="/analysis", tags=["insights"])
SEVERITY_ORDER = {
    Severity.CRITICAL: 0,
    Severity.HIGH: 1,
    Severity.MEDIUM: 2,
    Severity.LOW: 3,
}


@router.get("/{analysis_id}/insights")
def get_insights(
    severity: Severity | None = None,
    insight_type: InsightType | None = Query(default=None, alias="type"),
    provider: str | None = None,
    record: AnalysisRecord = Depends(require_analysis),
) -> dict:
    insights = record.result.insights
    if severity is not None:
        insights = [item for item in insights if item.severity == severity]
    if insight_type is not None:
        insights = [item for item in insights if item.type == insight_type]
    if provider is not None:
        normalised_provider = provider.upper()
        insights = [item for item in insights if item.segment.get("provider") == normalised_provider]
    insights = sorted(insights, key=lambda item: (SEVERITY_ORDER[item.severity], item.id))
    return {
        "analysis_id": record.analysis_id,
        "count": len(insights),
        "insights": [insight_payload(item) for item in insights],
    }


@router.get("/{analysis_id}/insights/{insight_id}")
def get_insight(
    insight_id: str,
    record: AnalysisRecord = Depends(require_analysis),
    explanation_provider: ExplanationProvider = Depends(get_explanation_provider),
) -> dict:
    insight = next((item for item in record.result.insights if item.id == insight_id), None)
    if insight is None:
        raise APIError(
            status_code=404,
            code="INSIGHT_NOT_FOUND",
            message="The requested insight does not exist in this analysis.",
        )
    return {
        "analysis_id": record.analysis_id,
        "insight": insight_payload(insight),
        "explanation": explanation_provider.explain(insight).model_dump(),
    }


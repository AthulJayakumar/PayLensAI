"""Single-read dashboard projection for large persisted analyses."""

from fastapi import APIRouter, Depends

from app.analytics.cash_flow import monthly_cash_flow
from app.analytics.models import SegmentDimension, SegmentMetrics
from app.analytics.segmentation import segment_metrics_by_dimension
from app.api.dependencies import require_analysis
from app.api.repositories import AnalysisRecord
from app.api.routes.analysis import analysis_summary
from app.api.routes.insights import SEVERITY_ORDER
from app.api.serialization import insight_payload, metrics_payload


router = APIRouter(prefix="/analysis", tags=["dashboard"])
DASHBOARD_DIMENSIONS = (
    SegmentDimension.PROVIDER,
    SegmentDimension.PAYMENT_METHOD,
    SegmentDimension.CARD_NETWORK,
    SegmentDimension.ISSUER_COUNTRY,
)


def _segments(
    record: AnalysisRecord,
    dimension: SegmentDimension,
    groups: list[SegmentMetrics],
) -> dict:
    """Build one segment panel from the already-loaded canonical transactions."""
    return {
        "analysis_id": record.analysis_id,
        "dimensions": [dimension.value],
        "segments": [
            {"segment": group.segment, **metrics_payload(group.metrics)}
            for group in groups
        ],
    }


@router.get("/{analysis_id}/dashboard")
def get_dashboard(record: AnalysisRecord = Depends(require_analysis)) -> dict:
    """Return every dashboard panel after loading the persisted analysis once.

    The former browser workflow made seven concurrent requests. Each request
    independently loaded and validated every Stripe transaction from PostgreSQL,
    which could exceed the edge timeout for provider-sized analyses.
    """
    insights = sorted(
        record.result.insights,
        key=lambda item: (SEVERITY_ORDER[item.severity], item.id),
    )
    # Group all dashboard dimensions during one traversal of the transaction list.
    grouped_segments = segment_metrics_by_dimension(record.transactions, DASHBOARD_DIMENSIONS)
    return {
        "summary": analysis_summary(record),
        "kpis": {
            "analysis_id": record.analysis_id,
            **metrics_payload(record.result.kpis),
        },
        "insights": {
            "analysis_id": record.analysis_id,
            "count": len(insights),
            "insights": [insight_payload(item) for item in insights],
        },
        # Cash flow is accumulated once and kept per currency and provider.
        "monthly_cash_flow": monthly_cash_flow(record.transactions),
        "performance": {
            dimension.value: _segments(record, dimension, grouped_segments[dimension])
            for dimension in DASHBOARD_DIMENSIONS
        },
    }

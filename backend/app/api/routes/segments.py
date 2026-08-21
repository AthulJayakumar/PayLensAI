from fastapi import APIRouter, Depends, Query

from app.analytics.models import SegmentDimension
from app.analytics.segmentation import segment_metrics
from app.api.dependencies import require_analysis
from app.api.errors import APIError
from app.api.repositories import AnalysisRecord
from app.api.serialization import metrics_payload


router = APIRouter(prefix="/analysis", tags=["segments"])


@router.get("/{analysis_id}/segments")
def get_segments(
    dimensions: str = Query(..., min_length=1),
    record: AnalysisRecord = Depends(require_analysis),
) -> dict:
    requested = [item.strip() for item in dimensions.split(",") if item.strip()]
    if not requested or len(requested) > 3 or len(set(requested)) != len(requested):
        raise APIError(
            status_code=422,
            code="INVALID_SEGMENT_DIMENSIONS",
            message="Provide between one and three unique segment dimensions.",
        )
    try:
        parsed = [SegmentDimension(item) for item in requested]
    except ValueError as error:
        raise APIError(
            status_code=422,
            code="INVALID_SEGMENT_DIMENSIONS",
            message="One or more segment dimensions are unsupported.",
            details=[{"supported": [item.value for item in SegmentDimension]}],
        ) from error

    groups = segment_metrics(record.transactions, parsed)
    return {
        "analysis_id": record.analysis_id,
        "dimensions": requested,
        "segments": [
            {"segment": group.segment, **metrics_payload(group.metrics)} for group in groups
        ],
    }


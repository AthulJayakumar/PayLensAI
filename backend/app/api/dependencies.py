"""FastAPI dependencies for repositories and stored analyses."""

from __future__ import annotations

from fastapi import Request

from app.api.errors import APIError
from app.api.explanations import ExplanationProvider
from app.api.repositories import AnalysisRecord, AnalysisRepository
from app.api.services.analysis import AnalysisService


def get_repository(request: Request) -> AnalysisRepository:
    return request.app.state.analysis_repository


def get_analysis_service(request: Request) -> AnalysisService:
    return request.app.state.analysis_service


def get_explanation_provider(request: Request) -> ExplanationProvider:
    return request.app.state.explanation_provider


def require_analysis(analysis_id: str, request: Request) -> AnalysisRecord:
    record = get_repository(request).get(analysis_id)
    if record is None:
        raise APIError(
            status_code=404,
            code="ANALYSIS_NOT_FOUND",
            message="The requested analysis does not exist or has expired.",
        )
    return record


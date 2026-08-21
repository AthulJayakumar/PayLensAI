"""FastAPI dependencies for repositories and stored analyses."""

from __future__ import annotations

from fastapi import Depends, Request

from app.api.auth import AuthenticatedMerchant
from app.api.errors import APIError
from app.api.explanations import ExplanationProvider
from app.api.repositories import AnalysisRecord, AnalysisRepository
from app.api.services.analysis import AnalysisService
from app.api.services.providers import ProviderService


def get_repository(request: Request) -> AnalysisRepository:
    return request.app.state.analysis_repository


def get_analysis_service(request: Request) -> AnalysisService:
    return request.app.state.analysis_service


def get_provider_service(request: Request) -> ProviderService:
    return request.app.state.provider_service


def get_explanation_provider(request: Request) -> ExplanationProvider:
    return request.app.state.explanation_provider


def get_current_merchant(request: Request) -> AuthenticatedMerchant:
    merchant = request.app.state.authenticator.authenticate(request)
    get_repository(request).ensure_merchant(merchant.merchant_id, merchant.name)
    return merchant


def require_analysis(
    analysis_id: str,
    request: Request,
    merchant: AuthenticatedMerchant = Depends(get_current_merchant),
) -> AnalysisRecord:
    record = get_repository(request).get_for_merchant(analysis_id, merchant.merchant_id)
    if record is None:
        raise APIError(
            status_code=404,
            code="ANALYSIS_NOT_FOUND",
            message="The requested analysis does not exist or has expired.",
        )
    return record

"""FastAPI application factory for the local PayLens prototype."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.errors import install_error_handlers
from app.api.explanations import ExplanationProvider, TemplateExplanationProvider
from app.api.repositories import AnalysisRepository, InMemoryAnalysisRepository
from app.api.routes import analysis, health, insights, kpis, segments
from app.api.services.analysis import AnalysisService, DEFAULT_MAX_UPLOAD_BYTES


def create_app(
    *,
    repository: AnalysisRepository | None = None,
    explanation_provider: ExplanationProvider | None = None,
    max_upload_bytes: int = DEFAULT_MAX_UPLOAD_BYTES,
) -> FastAPI:
    app = FastAPI(
        title="PayLens API",
        description="Local deterministic payment-intelligence prototype",
        version="0.3.0",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type"],
    )
    app.state.analysis_repository = repository or InMemoryAnalysisRepository()
    app.state.explanation_provider = explanation_provider or TemplateExplanationProvider()
    app.state.analysis_service = AnalysisService(
        app.state.analysis_repository, max_upload_bytes=max_upload_bytes
    )
    install_error_handlers(app)
    app.include_router(health.router)
    app.include_router(analysis.router)
    app.include_router(kpis.router)
    app.include_router(segments.router)
    app.include_router(insights.router)
    return app


app = create_app()


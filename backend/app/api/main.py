"""FastAPI application factory for the local PayLens prototype."""

from __future__ import annotations

import os
import secrets

from cryptography.fernet import Fernet
from dotenv import load_dotenv

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.errors import install_error_handlers
from app.api.auth import Authenticator, DevelopmentApiKeyAuthenticator
from app.api.explanations import ExplanationProvider, TemplateExplanationProvider
from app.api.repositories import AnalysisRepository, InMemoryAnalysisRepository
from app.api.routes import analysis, health, insights, kpis, providers, segments, webhooks
from app.api.services.analysis import AnalysisService, DEFAULT_MAX_UPLOAD_BYTES
from app.api.services.providers import ProviderService
from app.persistence.analysis_repository import PostgreSQLAnalysisRepository
from app.persistence.database import create_engine_from_url
from app.persistence.provider_repository import PostgreSQLRawProviderDataStore, SQLProviderRepository
from app.providers.raw_storage import InMemoryRawProviderDataStore
from app.providers.repository import InMemoryProviderRepository
from app.providers.security import CredentialCipher, CredentialVault, OAuthStateManager
from app.providers.stripe.connector import StripeConnector


load_dotenv()


def create_app(
    *,
    repository: AnalysisRepository | None = None,
    authenticator: Authenticator | None = None,
    provider_service: ProviderService | None = None,
    explanation_provider: ExplanationProvider | None = None,
    max_upload_bytes: int = DEFAULT_MAX_UPLOAD_BYTES,
) -> FastAPI:
    app = FastAPI(
        title="PayLens API",
        description="Local deterministic payment-intelligence prototype",
        version="0.4.0",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "X-PayLens-Dev-Key", "Stripe-Signature"],
    )
    engine = create_engine_from_url(os.environ["DATABASE_URL"]) if os.environ.get("DATABASE_URL") else None
    if engine is not None:
        required_local_security = [
            name
            for name in (
                "PAYLENS_DEV_API_KEY",
                "PAYLENS_CREDENTIAL_ENCRYPTION_KEY",
                "PAYLENS_OAUTH_STATE_SECRET",
            )
            if not os.environ.get(name)
        ]
        if required_local_security:
            raise RuntimeError(
                "Persistent mode requires security variables: " + ", ".join(required_local_security)
            )
    if repository is None and engine is not None:
        repository = PostgreSQLAnalysisRepository(engine)
    app.state.analysis_repository = repository or InMemoryAnalysisRepository()
    app.state.authenticator = authenticator or DevelopmentApiKeyAuthenticator.from_environment()
    app.state.explanation_provider = explanation_provider or TemplateExplanationProvider()
    app.state.analysis_service = AnalysisService(
        app.state.analysis_repository, max_upload_bytes=max_upload_bytes
    )
    if provider_service is None:
        provider_repository = SQLProviderRepository(engine) if engine is not None else InMemoryProviderRepository()
        raw_store = PostgreSQLRawProviderDataStore(engine) if engine is not None else InMemoryRawProviderDataStore()
        cipher_key = os.environ.get("PAYLENS_CREDENTIAL_ENCRYPTION_KEY") or Fernet.generate_key().decode()
        state_secret = os.environ.get("PAYLENS_OAUTH_STATE_SECRET") or secrets.token_urlsafe(48)
        client_id = os.environ.get("STRIPE_APP_CLIENT_ID")
        developer_key = os.environ.get("STRIPE_APP_DEVELOPER_API_KEY")
        connector = (
            StripeConnector(client_id=client_id, developer_api_key=developer_key)
            if client_id and developer_key
            else None
        )
        provider_service = ProviderService(
            connector=connector,
            repository=provider_repository,
            raw_store=raw_store,
            credential_vault=CredentialVault(CredentialCipher(cipher_key), provider_repository),
            state_manager=OAuthStateManager(state_secret, provider_repository),
            analysis_service=app.state.analysis_service,
            redirect_uri=os.environ.get("STRIPE_OAUTH_REDIRECT_URI", "http://localhost:8000/providers/stripe/oauth/callback"),
            webhook_secret=os.environ.get("STRIPE_WEBHOOK_SECRET"),
        )
    app.state.provider_service = provider_service
    install_error_handlers(app)
    app.include_router(health.router)
    app.include_router(analysis.router)
    app.include_router(kpis.router)
    app.include_router(segments.router)
    app.include_router(insights.router)
    app.include_router(providers.router)
    app.include_router(webhooks.router)
    return app


app = create_app()

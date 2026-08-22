"""FastAPI application factory for the local PayLens prototype."""

from __future__ import annotations

import os
import secrets
import logging
from urllib.parse import quote_plus

from cryptography.fernet import Fernet
from dotenv import load_dotenv

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.errors import install_error_handlers
from app.api.auth import Authenticator, CognitoAuthenticator, DevelopmentApiKeyAuthenticator
from app.api.explanations import ExplanationProvider, TemplateExplanationProvider
from app.api.repositories import AnalysisRepository, InMemoryAnalysisRepository
from app.api.routes import analysis, auth_config, health, insights, jobs, kpis, providers, segments, webhooks
from app.api.middleware import SecurityObservabilityMiddleware
from app.api.services.analysis import AnalysisService, DEFAULT_MAX_UPLOAD_BYTES
from app.api.services.providers import ProviderService
from app.persistence.analysis_repository import PostgreSQLAnalysisRepository
from app.persistence.database import create_engine_from_url
from app.persistence.provider_repository import PostgreSQLRawProviderDataStore, SQLProviderRepository
from app.persistence.pilot_repository import InMemoryPilotRepository, SQLPilotRepository
from app.providers.s3_storage import S3RawProviderDataStore
from app.providers.raw_storage import InMemoryRawProviderDataStore
from app.providers.repository import InMemoryProviderRepository
from app.providers.security import CredentialCipher, CredentialVault, OAuthStateManager
from app.providers.stripe.connector import StripeConnector


load_dotenv()


def _database_url() -> str | None:
    if os.environ.get("DATABASE_URL"):
        return os.environ["DATABASE_URL"]
    if os.environ.get("DB_HOST"):
        return (f"postgresql+psycopg://{quote_plus(os.environ['DB_USERNAME'])}:{quote_plus(os.environ['DB_PASSWORD'])}"
                f"@{os.environ['DB_HOST']}:{os.environ.get('DB_PORT', '5432')}/{os.environ.get('DB_NAME', 'paylens')}"
                "?sslmode=require")
    return None


def create_app(
    *,
    repository: AnalysisRepository | None = None,
    authenticator: Authenticator | None = None,
    provider_service: ProviderService | None = None,
    explanation_provider: ExplanationProvider | None = None,
    max_upload_bytes: int = DEFAULT_MAX_UPLOAD_BYTES,
) -> FastAPI:
    environment = os.environ.get("PAYLENS_ENV", "local").lower()
    app = FastAPI(
        title="PayLens API",
        description="Local deterministic payment-intelligence prototype",
        version="0.5.0",
        root_path=os.environ.get("PAYLENS_ROOT_PATH", ""),
    )
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"), format="%(message)s")
    app.add_middleware(SecurityObservabilityMiddleware, requests_per_minute=int(os.environ.get("PAYLENS_RATE_LIMIT_PER_MINUTE", "120")))
    origins = [item.strip() for item in os.environ.get("PAYLENS_CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",") if item.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=environment not in {"local", "test"},
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-PayLens-Dev-Key", "Stripe-Signature", "X-Request-ID"],
    )
    database_url = _database_url()
    engine = create_engine_from_url(database_url) if database_url else None
    app.state.database_engine = engine
    if engine is not None:
        required_local_security = [
            name
            for name in (
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
    pilot_repository = SQLPilotRepository(engine) if engine is not None else InMemoryPilotRepository()
    if authenticator is None:
        if environment in {"local", "test"}:
            authenticator = DevelopmentApiKeyAuthenticator.from_environment()
        else:
            required_cognito = [name for name in ("AWS_REGION", "COGNITO_USER_POOL_ID", "COGNITO_CLIENT_ID") if not os.environ.get(name)]
            if required_cognito:
                raise RuntimeError("Deployed mode requires Cognito variables: " + ", ".join(required_cognito))
            authenticator = CognitoAuthenticator(region=os.environ["AWS_REGION"], user_pool_id=os.environ["COGNITO_USER_POOL_ID"], client_id=os.environ["COGNITO_CLIENT_ID"], memberships=pilot_repository)
    app.state.authenticator = authenticator
    app.state.pilot_repository = pilot_repository
    app.state.explanation_provider = explanation_provider or TemplateExplanationProvider()
    app.state.analysis_service = AnalysisService(
        app.state.analysis_repository, max_upload_bytes=max_upload_bytes, audit_store=pilot_repository
    )
    if provider_service is None:
        provider_repository = SQLProviderRepository(engine) if engine is not None else InMemoryProviderRepository()
        if os.environ.get("PAYLENS_RAW_BUCKET"):
            raw_store = S3RawProviderDataStore(bucket=os.environ["PAYLENS_RAW_BUCKET"], kms_key_id=os.environ["PAYLENS_RAW_KMS_KEY_ID"])
        else:
            raw_store = PostgreSQLRawProviderDataStore(engine) if engine is not None else InMemoryRawProviderDataStore()
        cipher_key = os.environ.get("PAYLENS_CREDENTIAL_ENCRYPTION_KEY") or Fernet.generate_key().decode()
        state_secret = os.environ.get("PAYLENS_OAUTH_STATE_SECRET") or secrets.token_urlsafe(48)
        client_id = os.environ.get("STRIPE_APP_CLIENT_ID")
        developer_key = os.environ.get("STRIPE_APP_DEVELOPER_API_KEY")
        if client_id == "NOT_CONFIGURED": client_id = None
        if developer_key == "NOT_CONFIGURED": developer_key = None
        webhook_secret = os.environ.get("STRIPE_WEBHOOK_SECRET")
        if webhook_secret == "NOT_CONFIGURED": webhook_secret = None
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
            webhook_secret=webhook_secret,
            audit_store=pilot_repository,
        )
    app.state.provider_service = provider_service
    app.state.job_service = None
    app.state.analysis_upload_store = None
    if os.environ.get("PAYLENS_PROVIDER_SYNC_QUEUE_URL"):
        from app.jobs import JobService, S3AnalysisUploadStore, SQSJobQueue
        from app.providers.models import JobType
        queue_urls = {JobType.PROVIDER_SYNC: os.environ["PAYLENS_PROVIDER_SYNC_QUEUE_URL"]}
        if os.environ.get("PAYLENS_ANALYSIS_QUEUE_URL"): queue_urls[JobType.ANALYSIS] = os.environ["PAYLENS_ANALYSIS_QUEUE_URL"]
        if os.environ.get("PAYLENS_WEBHOOK_QUEUE_URL"): queue_urls[JobType.WEBHOOK] = os.environ["PAYLENS_WEBHOOK_QUEUE_URL"]
        app.state.job_service = JobService(pilot_repository, SQSJobQueue(queue_urls))
        if os.environ.get("PAYLENS_RAW_BUCKET"):
            app.state.analysis_upload_store = S3AnalysisUploadStore(bucket=os.environ["PAYLENS_RAW_BUCKET"], kms_key_id=os.environ["PAYLENS_RAW_KMS_KEY_ID"])
    install_error_handlers(app)
    app.include_router(health.router)
    api_prefix = os.environ.get("PAYLENS_API_PREFIX", "")
    app.include_router(auth_config.router, prefix=api_prefix)
    app.include_router(analysis.router, prefix=api_prefix)
    app.include_router(kpis.router, prefix=api_prefix)
    app.include_router(segments.router, prefix=api_prefix)
    app.include_router(insights.router, prefix=api_prefix)
    app.include_router(jobs.router, prefix=api_prefix)
    app.include_router(providers.router, prefix=api_prefix)
    app.include_router(webhooks.router, prefix=api_prefix)
    return app


app = create_app()

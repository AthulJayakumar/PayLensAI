from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from datetime import datetime, timedelta, timezone

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from app.api.auth import AuthenticatedMerchant, StaticAuthenticator
from app.api.errors import APIError
from app.api.main import create_app
from app.api.repositories import InMemoryAnalysisRepository
from app.api.services.analysis import AnalysisService
from app.api.services.providers import ProviderService
from app.models import DataAvailability, PaymentStatus, SourceType
from app.persistence.analysis_repository import PostgreSQLAnalysisRepository
from app.persistence.database import Base, create_engine_from_url
from app.persistence.provider_repository import PostgreSQLRawProviderDataStore, SQLProviderRepository
from app.providers.models import ConnectionStatus, OAuthTokenResponse, ProviderConnection, RawProviderObject, SyncStatus
from app.providers.raw_storage import InMemoryRawProviderDataStore
from app.providers.repository import InMemoryProviderRepository
from app.providers.security import CredentialCipher, CredentialVault, OAuthStateManager
from app.providers.stripe.connector import StripeConnector, StripeTransport
from app.providers.stripe.normalizer import StripeNormalizer
from app.synthetic.config import GenerationConfig
from app.synthetic.csv_export import export_transactions_csv
from app.synthetic.generator import generate_transactions


MERCHANT_A = AuthenticatedMerchant(merchant_id="merchant_a", name="Merchant A")
STATE_SECRET = "state-secret-with-more-than-thirty-two-characters"
WEBHOOK_SECRET = "whsec_sprint4_test_secret"


def stripe_intent(
    intent_id: str,
    *,
    status: str = "succeeded",
    amount: int = 1250,
    created: int = 1_782_000_000,
) -> dict:
    failed = status == "requires_payment_method"
    return {
        "id": intent_id,
        "object": "payment_intent",
        "amount": amount,
        "amount_received": amount if status == "succeeded" else 0,
        "currency": "gbp",
        "created": created,
        "status": status,
        "payment_method_types": ["card"],
        "last_payment_error": (
            {"code": "card_declined", "decline_code": "insufficient_funds", "message": "Declined"}
            if failed
            else None
        ),
        "latest_charge": {
            "id": f"ch_{intent_id}",
            "amount": amount,
            "amount_refunded": 0,
            "disputed": False,
            "payment_method_details": {
                "type": "card",
                "card": {"brand": "mastercard", "funding": "debit", "country": "US"},
            },
            "balance_transaction": {"fee": 66, "currency": "gbp"},
        },
    }


class FakeStripeTransport(StripeTransport):
    def __init__(self, pages: dict[str | None, dict] | None = None) -> None:
        self.pages = pages or {None: {"data": [stripe_intent("pi_1")], "has_more": False}}
        self.calls: list[dict] = []
        self.access_tokens: list[str] = []
        self.fail_cursor: str | None = None
        self.fail_once = False
        self.retrieve_payload = stripe_intent("pi_1")

    def exchange_token(self, developer_api_key: str, form: dict[str, str]) -> dict:
        token_suffix = "refreshed" if form["grant_type"] == "refresh_token" else "initial"
        return {
            "access_token": f"access_{token_suffix}",
            "refresh_token": f"refresh_{token_suffix}",
            "stripe_user_id": "acct_sandbox_merchant_a",
            "scope": "stripe_apps",
            "livemode": False,
        }

    def list_payment_intents(self, access_token: str, params: dict) -> dict:
        self.access_tokens.append(access_token)
        self.calls.append(params)
        cursor = params.get("starting_after")
        if self.fail_once and cursor == self.fail_cursor:
            self.fail_once = False
            raise RuntimeError("simulated provider outage containing no payload")
        return self.pages[cursor]

    def retrieve_payment_intent(self, access_token: str, transaction_id: str) -> dict:
        return self.retrieve_payload

    def retrieve_account(self, access_token: str) -> dict:
        return {"id": "acct_sandbox_merchant_a"}


def provider_context(
    *, pages: dict[str | None, dict] | None = None
) -> tuple[ProviderService, FakeStripeTransport, InMemoryProviderRepository, InMemoryRawProviderDataStore, InMemoryAnalysisRepository]:
    transport = FakeStripeTransport(pages)
    connector = StripeConnector(client_id="ca_test_paylens", developer_api_key="sk_test_platform", transport=transport)
    provider_repository = InMemoryProviderRepository()
    raw_store = InMemoryRawProviderDataStore()
    analysis_repository = InMemoryAnalysisRepository()
    service = ProviderService(
        connector=connector,
        repository=provider_repository,
        raw_store=raw_store,
        credential_vault=CredentialVault(CredentialCipher(Fernet.generate_key().decode()), provider_repository),
        state_manager=OAuthStateManager(STATE_SECRET, provider_repository),
        analysis_service=AnalysisService(analysis_repository),
        redirect_uri="http://localhost:8000/providers/stripe/oauth/callback",
        webhook_secret=WEBHOOK_SECRET,
    )
    state = service.state_manager.issue(MERCHANT_A.merchant_id)
    service.complete_authorization(code="ac_test", state=state)
    return service, transport, provider_repository, raw_store, analysis_repository


def stripe_signature(payload: bytes, secret: str = WEBHOOK_SECRET) -> str:
    timestamp = int(time.time())
    signature = hmac.new(secret.encode(), f"{timestamp}.{payload.decode()}".encode(), hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={signature}"


def test_development_authentication_is_required() -> None:
    response = TestClient(create_app()).get("/providers")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"


def test_cross_merchant_analysis_access_is_denied(tmp_path) -> None:
    output = tmp_path / "merchant.csv"
    export_transactions_csv(generate_transactions(GenerationConfig(count=50, seed=404)), output)
    repository = InMemoryAnalysisRepository()
    client = TestClient(create_app(repository=repository))
    key_a = "merchant-a-development-key"
    key_b = "merchant-b-development-key"
    upload = client.post(
        "/analysis/upload",
        headers={"X-PayLens-Dev-Key": key_a},
        files={"file": ("merchant.csv", output.read_bytes(), "text/csv")},
    )
    assert upload.status_code == 201
    analysis_id = upload.json()["analysis_id"]
    assert client.get(f"/analysis/{analysis_id}", headers={"X-PayLens-Dev-Key": key_a}).status_code == 200
    denied = client.get(f"/analysis/{analysis_id}", headers={"X-PayLens-Dev-Key": key_b})
    assert denied.status_code == 404
    denied_insights = client.get(f"/analysis/{analysis_id}/insights", headers={"X-PayLens-Dev-Key": key_b})
    assert denied_insights.status_code == 404


def test_stripe_apps_oauth_url_and_one_time_state() -> None:
    service, _, _, _, _ = provider_context()
    state = service.state_manager.issue(MERCHANT_A.merchant_id)
    url = service.connector.authorize(state=state, redirect_uri=service.redirect_uri)
    assert url.startswith("https://marketplace.stripe.com/oauth/v2/authorize?")
    assert "client_id=ca_test_paylens" in url and "state=" in url
    assert service.state_manager.consume(state) == MERCHANT_A.merchant_id
    with pytest.raises(ValueError, match="already used"):
        service.state_manager.consume(state)


def test_private_sandbox_connection_verifies_and_encrypts_restricted_key() -> None:
    transport = FakeStripeTransport()
    connector = StripeConnector(
        sandbox_api_key="rk_test_paylens_private",
        sandbox_account_id="acct_sandbox_merchant_a",
        transport=transport,
    )
    repository = InMemoryProviderRepository()
    vault = CredentialVault(CredentialCipher(Fernet.generate_key().decode()), repository)
    service = ProviderService(
        connector=connector,
        repository=repository,
        raw_store=InMemoryRawProviderDataStore(),
        credential_vault=vault,
        state_manager=OAuthStateManager(STATE_SECRET, repository),
        analysis_service=AnalysisService(InMemoryAnalysisRepository()),
        redirect_uri="http://localhost:8000/providers/stripe/oauth/callback",
        webhook_secret=WEBHOOK_SECRET,
    )

    client = TestClient(create_app(provider_service=service, authenticator=StaticAuthenticator(MERCHANT_A)))
    response = client.post("/providers/stripe/connect-sandbox")

    assert response.status_code == 200
    assert response.json()["connection"]["connection_mode"] == "SANDBOX_KEY"
    connection = service.status(MERCHANT_A.merchant_id)
    assert connection is not None
    assert connection.provider_account_id == "acct_sandbox_merchant_a"
    stored = repository.get_encrypted_credentials(connection.id)
    assert stored is not None and "rk_test_paylens_private" not in stored[0]
    assert vault.load(connection.id) == ("rk_test_paylens_private", None)
    status_response = client.get("/providers").json()["providers"][0]
    assert status_response["configured"] is True
    assert status_response["connection_mode"] == "SANDBOX_KEY"
    sync_job = service.sync(MERCHANT_A)
    assert sync_job.status == SyncStatus.COMPLETED
    assert transport.access_tokens == ["rk_test_paylens_private"]
    standalone_event = {
        "id": "evt_private_sandbox",
        "object": "event",
        "type": "payment_intent.succeeded",
        "data": {"object": stripe_intent("pi_private_webhook")},
    }
    payload = json.dumps(standalone_event, separators=(",", ":")).encode()
    assert service.process_webhook(payload, stripe_signature(payload))["status"] == "processed"
    oauth_response = client.post("/providers/stripe/authorize")
    assert oauth_response.status_code == 409
    assert oauth_response.json()["error"]["code"] == "STRIPE_OAUTH_DISABLED"


def test_private_sandbox_connection_rejects_wrong_account() -> None:
    transport = FakeStripeTransport()
    connector = StripeConnector(
        sandbox_api_key="rk_test_paylens_private",
        sandbox_account_id="acct_different",
        transport=transport,
    )
    with pytest.raises(ValueError, match="does not belong"):
        connector.verify_sandbox_credentials()


@pytest.mark.parametrize("api_key", ["rk_live_forbidden", "sk_test_too_broad"])
def test_private_sandbox_connector_rejects_live_or_unrestricted_keys(api_key: str) -> None:
    with pytest.raises(ValueError, match="restricted test key"):
        StripeConnector(sandbox_api_key=api_key, sandbox_account_id="acct_live")


def test_credentials_are_encrypted_before_storage() -> None:
    service, _, repository, _, _ = provider_context()
    connection = service.status(MERCHANT_A.merchant_id)
    stored = repository.get_encrypted_credentials(connection.id)
    assert stored is not None
    assert "access_initial" not in stored[0]
    assert "refresh_initial" not in (stored[1] or "")
    assert service.credential_vault.load(connection.id) == ("access_initial", "refresh_initial")


def test_connector_refreshes_rotating_oauth_tokens() -> None:
    service, _, _, _, _ = provider_context()
    tokens = service.connector.refresh_credentials("refresh_initial")
    assert tokens.access_token == "access_refreshed"
    assert tokens.refresh_token == "refresh_refreshed"
    assert tokens.provider_account_id == "acct_sandbox_merchant_a"


def test_stripe_normalizer_maps_available_fields_without_fabrication() -> None:
    transaction = StripeNormalizer().normalize(
        stripe_intent("pi_normalized"), merchant_id="merchant_a", raw_reference="raw_1", source=SourceType.API
    )
    assert transaction.provider_transaction_id == "pi_normalized"
    assert transaction.status == PaymentStatus.SUCCEEDED
    assert transaction.amount == transaction.gross_amount
    assert transaction.processing_fee > 0
    assert transaction.card_network.value == "MASTERCARD"
    assert transaction.issuer_country == "US"
    assert transaction.raw_data_reference == "raw_1"
    assert transaction.data_availability["settlement_date"] == DataAvailability.NOT_AVAILABLE
    assert transaction.settlement_date is None
    assert transaction.provider_fee == 0


def test_failed_stripe_payment_maps_failure_details() -> None:
    transaction = StripeNormalizer().normalize(
        stripe_intent("pi_failed", status="requires_payment_method"),
        merchant_id="merchant_a", raw_reference="raw_failed", source=SourceType.WEBHOOK,
    )
    assert transaction.status == PaymentStatus.FAILED
    assert transaction.failure_category.value == "INSUFFICIENT_FUNDS"
    assert transaction.provider_failure_code == "card_declined"


def test_stripe_normalizer_accepts_missing_optional_fields() -> None:
    minimal = {
        "id": "pi_minimal", "amount": 500, "currency": "jpy",
        "created": 1_782_000_000, "status": "processing",
    }
    transaction = StripeNormalizer().normalize(
        minimal, merchant_id="merchant_a", raw_reference="raw_minimal", source=SourceType.API
    )
    assert transaction.amount == 500
    assert transaction.status == PaymentStatus.PENDING
    assert transaction.card_network is None
    assert transaction.settlement_date is None


def test_historical_sync_paginates_preserves_raw_and_runs_analytics() -> None:
    pages = {
        None: {"data": [stripe_intent("pi_1"), stripe_intent("pi_2")], "has_more": True},
        "pi_2": {"data": [stripe_intent("pi_3")], "has_more": False},
    }
    service, transport, repository, raw_store, analyses = provider_context(pages=pages)
    job = service.sync(MERCHANT_A)
    assert job.status == SyncStatus.COMPLETED
    assert job.records_received == job.records_normalised == 3
    assert [call.get("starting_after") for call in transport.calls] == [None, "pi_2"]
    assert len(repository.list_canonical(MERCHANT_A.merchant_id, "STRIPE")) == 3
    assert raw_store.get("raw_" + hashlib.sha256(b"merchant_a:STRIPE:payment_intent:pi_1").hexdigest()[:32], "merchant_a").payload["id"] == "pi_1"
    analysis = analyses.get_for_merchant(job.analysis_id, MERCHANT_A.merchant_id)
    assert analysis is not None and analysis.source == "STRIPE" and analysis.result.transaction_count == 3


def test_partial_sync_is_retry_safe_and_resumable() -> None:
    pages = {
        None: {"data": [stripe_intent("pi_first")], "has_more": True},
        "pi_first": {"data": [stripe_intent("pi_second")], "has_more": False},
    }
    service, transport, repository, _, _ = provider_context(pages=pages)
    transport.fail_cursor = "pi_first"
    transport.fail_once = True
    partial = service.sync(MERCHANT_A)
    assert partial.status == SyncStatus.PARTIAL
    assert partial.records_received == 1 and partial.cursor == "pi_first"
    completed = service.sync(MERCHANT_A, resume_job_id=partial.id)
    assert completed.status == SyncStatus.COMPLETED
    assert completed.records_received == 2
    assert len(repository.list_canonical("merchant_a", "STRIPE")) == 2


def test_invalid_webhook_signature_is_rejected() -> None:
    service, _, _, _, _ = provider_context()
    payload = json.dumps({"id": "evt_invalid", "type": "payment_intent.succeeded"}).encode()
    with pytest.raises(APIError) as captured:
        service.process_webhook(payload, "t=1,v1=invalid")
    assert captured.value.code == "INVALID_WEBHOOK_SIGNATURE"


def test_duplicate_webhook_is_idempotent() -> None:
    service, _, repository, raw_store, _ = provider_context()
    event = {
        "id": "evt_duplicate",
        "object": "event",
        "account": "acct_sandbox_merchant_a",
        "type": "payment_intent.succeeded",
        "data": {"object": stripe_intent("pi_webhook")},
    }
    payload = json.dumps(event, separators=(",", ":")).encode()
    signature = stripe_signature(payload)
    first = service.process_webhook(payload, signature)
    second = service.process_webhook(payload, signature)
    assert first["status"] == "processed"
    assert second["status"] == "duplicate"
    assert len(repository.list_canonical("merchant_a", "STRIPE")) == 1
    raw_id = "raw_" + hashlib.sha256(b"merchant_a:STRIPE:event:evt_duplicate").hexdigest()[:32]
    assert raw_store.get(raw_id, "merchant_a") is not None


def test_webhook_endpoint_rejects_invalid_signature() -> None:
    service, _, _, _, _ = provider_context()
    app = create_app(provider_service=service, authenticator=StaticAuthenticator(MERCHANT_A))
    response = TestClient(app).post(
        "/webhooks/stripe", content=b"{}", headers={"Stripe-Signature": "bad"}
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_WEBHOOK_SIGNATURE"


def test_reconciliation_detects_repairs_and_duplicates() -> None:
    updated = stripe_intent("pi_updated", status="succeeded", amount=2000)
    missing = stripe_intent("pi_missing")
    pages = {None: {"data": [updated, missing, missing], "has_more": False}}
    service, _, repository, _, _ = provider_context(pages=pages)
    old = StripeNormalizer().normalize(
        stripe_intent("pi_updated", status="processing", amount=1000),
        merchant_id="merchant_a", raw_reference="raw_old", source=SourceType.API,
    )
    repository.upsert_canonical(old)
    result = service.reconcile("merchant_a")
    assert result.missing == ["pi_missing"]
    assert result.updated == ["pi_updated"]
    assert result.duplicates == ["pi_missing"]
    assert result.repaired == 2


def test_provider_status_and_disconnect_are_merchant_scoped() -> None:
    service, _, _, _, _ = provider_context()
    client = TestClient(create_app(provider_service=service, authenticator=StaticAuthenticator(MERCHANT_A)))
    status_response = client.get("/providers")
    assert status_response.status_code == 200
    assert status_response.json()["providers"][0]["status"] == ConnectionStatus.CONNECTED
    assert client.delete("/providers/stripe").status_code == 204
    assert client.get("/providers").json()["providers"][0]["status"] == "NOT_CONNECTED"


def test_provider_connection_is_not_visible_to_another_merchant() -> None:
    service, _, _, _, _ = provider_context()
    merchant_b = AuthenticatedMerchant(merchant_id="merchant_b", name="Merchant B")
    client = TestClient(create_app(provider_service=service, authenticator=StaticAuthenticator(merchant_b)))
    assert client.get("/providers").json()["providers"][0]["status"] == "NOT_CONNECTED"


@pytest.mark.skipif(not os.environ.get("PAYLENS_TEST_DATABASE_URL"), reason="PostgreSQL integration URL not configured")
def test_postgresql_repository_persists_owned_analysis(transaction_factory) -> None:
    engine = create_engine_from_url(os.environ["PAYLENS_TEST_DATABASE_URL"])
    Base.metadata.create_all(engine)
    unique = hashlib.sha256(str(time.time_ns()).encode()).hexdigest()[:12]
    merchant = AuthenticatedMerchant(merchant_id=f"merchant_pg_{unique}", name="Postgres Merchant")
    repository = PostgreSQLAnalysisRepository(engine)
    repository.ensure_merchant(merchant.merchant_id, merchant.name)
    transaction = transaction_factory(
        id=f"ptx_pg_{unique}", merchant_id=merchant.merchant_id,
        provider_transaction_id=f"pi_pg_{unique}",
    )
    record = AnalysisService(repository).create_from_transactions(
        [transaction], merchant, filename="postgres-integration", source="STRIPE"
    )
    loaded = repository.get_for_merchant(record.analysis_id, merchant.merchant_id)
    assert loaded is not None
    assert loaded.result.transaction_count == 1
    assert repository.get_for_merchant(record.analysis_id, "merchant_someone_else") is None


@pytest.mark.skipif(not os.environ.get("PAYLENS_TEST_DATABASE_URL"), reason="PostgreSQL integration URL not configured")
def test_postgresql_provider_credentials_are_ciphertext() -> None:
    engine = create_engine_from_url(os.environ["PAYLENS_TEST_DATABASE_URL"])
    Base.metadata.create_all(engine)
    repository = PostgreSQLAnalysisRepository(engine)
    unique = hashlib.sha256(str(time.time_ns()).encode()).hexdigest()[:12]
    merchant_id = f"merchant_cred_{unique}"
    repository.ensure_merchant(merchant_id, "Credential Merchant")
    providers = SQLProviderRepository(engine)
    now = datetime.now(timezone.utc)
    connection = ProviderConnection(
        id=f"connection_{unique}", merchant_id=merchant_id, provider="STRIPE",
        status=ConnectionStatus.CONNECTED, provider_account_id=f"acct_{unique}",
        created_at=now, updated_at=now,
    )
    providers.save_connection(connection)
    vault = CredentialVault(CredentialCipher(Fernet.generate_key().decode()), providers)
    vault.save(connection.id, "access-secret-value", "refresh-secret-value")
    stored = providers.get_encrypted_credentials(connection.id)
    assert stored and "access-secret-value" not in stored[0]
    assert vault.load(connection.id) == ("access-secret-value", "refresh-secret-value")


@pytest.mark.skipif(not os.environ.get("PAYLENS_TEST_DATABASE_URL"), reason="PostgreSQL integration URL not configured")
def test_postgresql_raw_jsonb_preserves_provider_payload() -> None:
    engine = create_engine_from_url(os.environ["PAYLENS_TEST_DATABASE_URL"])
    Base.metadata.create_all(engine)
    analysis_repository = PostgreSQLAnalysisRepository(engine)
    unique = hashlib.sha256(str(time.time_ns()).encode()).hexdigest()[:12]
    merchant_id = f"merchant_raw_{unique}"
    analysis_repository.ensure_merchant(merchant_id, "Raw Merchant")
    raw_store = PostgreSQLRawProviderDataStore(engine)
    payload = stripe_intent(f"pi_raw_{unique}")
    raw = RawProviderObject(
        id=f"raw_{unique}", merchant_id=merchant_id, provider="STRIPE",
        provider_object_type="payment_intent", provider_object_id=payload["id"],
        received_at=datetime.now(timezone.utc), source="HISTORICAL_SYNC",
        schema_version="stripe-payment-intent-v1", payload=payload,
    )
    raw_store.put(raw)
    loaded = raw_store.get(raw.id, merchant_id)
    assert loaded is not None and loaded.payload == payload
    assert raw_store.get(raw.id, "merchant_other") is None

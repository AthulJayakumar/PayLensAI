from __future__ import annotations

from datetime import datetime, timedelta, timezone
from io import BytesIO
from types import SimpleNamespace

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from app.api.auth import AuthenticatedMerchant, CognitoAuthenticator, MerchantRole, StaticAuthenticator
from app.api.errors import APIError
from app.api.main import create_app
from app.jobs import InMemoryJobQueue, JobService
from app.persistence.pilot_repository import AuditEvent, InMemoryPilotRepository
from app.providers.models import JobType, RawProviderObject
from app.providers.s3_storage import S3RawProviderDataStore
from app.providers.stripe.connector import StripeConnector, StripeTransport


class FakeS3:
    class exceptions:
        class NoSuchKey(Exception): pass

    def __init__(self): self.objects = {}
    def put_object(self, **request): self.objects[(request["Bucket"], request["Key"])] = request
    def get_object(self, Bucket, Key):
        request = self.objects.get((Bucket, Key))
        if request is None: raise self.exceptions.NoSuchKey()
        return {"Body": BytesIO(request["Body"])}


def raw(merchant_id="merchant_a"):
    return RawProviderObject(id="raw_1", merchant_id=merchant_id, provider="STRIPE", provider_object_type="payment_intent",
        provider_object_id="pi_sensitive", received_at=datetime(2026, 8, 23, tzinfo=timezone.utc), source="WEBHOOK",
        schema_version="stripe-v1", payload={"id": "pi_sensitive", "amount": 1000})


def test_s3_raw_store_is_encrypted_and_opaque() -> None:
    client = FakeS3(); store = S3RawProviderDataStore(bucket="raw", kms_key_id="kms-key", client=client)
    reference = store.put(raw())
    request = next(iter(client.objects.values()))
    assert request["ServerSideEncryption"] == "aws:kms" and request["SSEKMSKeyId"] == "kms-key"
    assert "merchant_a" not in reference and "pi_sensitive" not in reference
    assert store.get(reference, "merchant_a").payload["amount"] == 1000


def test_s3_store_rejects_cross_merchant_read() -> None:
    store = S3RawProviderDataStore(bucket="raw", kms_key_id="kms", client=FakeS3())
    reference = store.put(raw())
    assert store.get(reference, "merchant_b") is None


def test_job_deduplication_and_cross_merchant_isolation() -> None:
    repository, queue = InMemoryPilotRepository(), InMemoryJobQueue(); service = JobService(repository, queue)
    first = service.enqueue(merchant_id="merchant_a", job_type=JobType.PROVIDER_SYNC, deduplication_key="sync:1", payload={})
    second = service.enqueue(merchant_id="merchant_a", job_type=JobType.PROVIDER_SYNC, deduplication_key="sync:1", payload={})
    assert first.id == second.id and len(queue.messages) == 1
    assert service.get_owned(first.id, "merchant_b") is None


def test_audit_store_records_only_safe_metadata() -> None:
    repository = InMemoryPilotRepository(); repository.record(AuditEvent(merchant_id="merchant_a", event_type="SYNC_STARTED", resource="sync_1", safe_metadata={"count": 10}))
    assert repository.audit_events[0].safe_metadata == {"count": 10}


def cognito_auth(expiry: datetime):
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    repository = InMemoryPilotRepository(); repository.add_membership("subject-1", "merchant_a", "Merchant A", MerchantRole.ANALYST)
    auth = CognitoAuthenticator(region="eu-north-1", user_pool_id="eu-north-1_pool", client_id="client-1", memberships=repository)
    auth.jwks = SimpleNamespace(get_signing_key_from_jwt=lambda _: SimpleNamespace(key=private_key.public_key()))
    now = datetime.now(timezone.utc)
    token = jwt.encode({"iss": auth.issuer, "sub": "subject-1", "client_id": "client-1", "token_use": "access", "iat": int(now.timestamp()), "exp": int(expiry.timestamp())}, private_key, algorithm="RS256")
    return auth, token


def test_cognito_claims_resolve_server_side_membership() -> None:
    auth, token = cognito_auth(datetime.now(timezone.utc) + timedelta(minutes=5))
    request = SimpleNamespace(headers={"Authorization": f"Bearer {token}"})
    merchant = auth.authenticate(request)
    assert merchant.merchant_id == "merchant_a" and merchant.role == MerchantRole.ANALYST


def test_cognito_rejects_expired_token() -> None:
    auth, token = cognito_auth(datetime.now(timezone.utc) - timedelta(minutes=1))
    try: auth.authenticate(SimpleNamespace(headers={"Authorization": f"Bearer {token}"}))
    except APIError as error: assert error.code == "INVALID_TOKEN"
    else: raise AssertionError("expired Cognito token accepted")


def test_viewer_cannot_start_stripe_authorization() -> None:
    merchant = AuthenticatedMerchant(merchant_id="merchant_a", name="Merchant", role=MerchantRole.VIEWER)
    client = TestClient(create_app(authenticator=StaticAuthenticator(merchant)))
    response = client.post("/providers/stripe/authorize")
    assert response.status_code == 403 and response.json()["error"]["code"] == "ROLE_FORBIDDEN"


class RevokeTransport(StripeTransport):
    def exchange_token(self, developer_api_key, form): return {}
    def list_payment_intents(self, access_token, params): return {}
    def retrieve_payment_intent(self, access_token, transaction_id): return {}
    def deauthorize(self, developer_api_key, client_id, stripe_user_id): return {"stripe_user_id": stripe_user_id}


def test_stripe_provider_side_revocation() -> None:
    connector = StripeConnector(client_id="ca_test", developer_api_key="sk_test", transport=RevokeTransport())
    assert connector.revoke("acct_test") is True

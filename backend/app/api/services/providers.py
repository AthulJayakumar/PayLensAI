"""Provider authorization, synchronization, webhook, and reconciliation orchestration."""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from app.api.auth import AuthenticatedMerchant
from app.api.errors import APIError
from app.api.services.analysis import AnalysisService
from app.models import SourceType
from app.providers.models import (
    ConnectionStatus,
    ProviderConnection,
    ProviderCredentials,
    RawProviderObject,
    ReconciliationResult,
    SyncJob,
    SyncStatus,
)
from app.providers.security import CredentialVault, OAuthStateManager
from app.providers.stripe.normalizer import StripeNormalizer
from app.persistence.pilot_repository import AuditEvent


def _id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(12)}"


class ProviderService:
    """Coordinate Stripe without leaking provider details into analytics code."""
    def __init__(
        self,
        *,
        connector,
        repository,
        raw_store,
        credential_vault: CredentialVault,
        state_manager: OAuthStateManager,
        analysis_service: AnalysisService,
        redirect_uri: str,
        webhook_secret: str | None,
        normalizer: StripeNormalizer | None = None,
        audit_store=None,
    ) -> None:
        self.connector = connector
        self.repository = repository
        self.raw_store = raw_store
        self.credential_vault = credential_vault
        self.state_manager = state_manager
        self.analysis_service = analysis_service
        self.redirect_uri = redirect_uri
        self.webhook_secret = webhook_secret
        self.normalizer = normalizer or StripeNormalizer()
        self.audit_store = audit_store

    def _audit(self, merchant_id: str, event_type: str, resource: str, *, actor_id: str | None = None, metadata: dict | None = None) -> None:
        if self.audit_store is not None:
            self.audit_store.record(AuditEvent(merchant_id=merchant_id, actor_id=actor_id, event_type=event_type,
                                               resource=resource, safe_metadata=metadata or {}))

    def _configured_connector(self):
        if self.connector is None:
            raise APIError(status_code=503, code="STRIPE_NOT_CONFIGURED", message="Stripe App sandbox credentials are not configured.")
        return self.connector

    def status(self, merchant_id: str) -> ProviderConnection | None:
        return self.repository.get_connection(merchant_id, "STRIPE")

    def diagnostics(self, merchant_id: str) -> dict:
        """Return merchant-scoped operational state without provider payloads or credentials."""
        connection = self.status(merchant_id)
        latest_sync = self.repository.latest_sync_job(merchant_id, "STRIPE")
        latest_webhook = self.repository.latest_webhook_event(merchant_id, "STRIPE")
        canonical_count = len(self.repository.list_canonical(merchant_id, "STRIPE"))
        if connection is None:
            pipeline_status = "NOT_CONNECTED"
        elif connection.status != ConnectionStatus.CONNECTED:
            pipeline_status = "DEGRADED"
        elif latest_webhook and latest_webhook["processed_at"] is None:
            pipeline_status = "PROCESSING"
        elif latest_sync and latest_sync.status in {SyncStatus.FAILED, SyncStatus.PARTIAL}:
            pipeline_status = "DEGRADED"
        else:
            pipeline_status = "HEALTHY"
        return {
            "provider": "STRIPE",
            "pipeline_status": pipeline_status,
            "connection_status": connection.status.value if connection else "NOT_CONNECTED",
            "webhook_status": connection.webhook_status if connection else "NOT_CONFIGURED",
            "last_sync_at": connection.last_sync_at if connection else None,
            "transactions_imported": connection.transactions_imported if connection else 0,
            "canonical_transaction_count": canonical_count,
            "latest_sync": latest_sync.model_dump(mode="json") if latest_sync else None,
            "latest_webhook": latest_webhook,
        }

    def authorization_url(self, merchant_id: str) -> str:
        connector = self._configured_connector()
        if connector.connection_mode != "OAUTH":
            raise APIError(
                status_code=409,
                code="STRIPE_OAUTH_DISABLED",
                message="This PayLens environment uses a private Stripe sandbox connection.",
            )
        state = self.state_manager.issue(merchant_id)
        return connector.authorize(state=state, redirect_uri=self.redirect_uri)

    def connect_sandbox(self, merchant_id: str, *, actor_id: str | None = None) -> ProviderConnection:
        """Verify and encrypt the server-held key for this pilot merchant."""
        connector = self._configured_connector()
        if connector.connection_mode != "SANDBOX_KEY":
            raise APIError(
                status_code=409,
                code="STRIPE_SANDBOX_KEY_DISABLED",
                message="This PayLens environment uses Stripe App OAuth.",
            )
        try:
            credentials = connector.verify_sandbox_credentials()
        except Exception as error:
            raise APIError(
                status_code=502,
                code="STRIPE_SANDBOX_CONNECTION_FAILED",
                message="Stripe did not accept the configured sandbox credential.",
            ) from error
        claimed = self.repository.find_connection_by_account("STRIPE", credentials.provider_account_id)
        if claimed is not None and claimed.merchant_id != merchant_id:
            raise APIError(
                status_code=409,
                code="STRIPE_SANDBOX_ALREADY_CONNECTED",
                message="This Stripe sandbox is already assigned to another PayLens merchant.",
            )
        now = datetime.now(timezone.utc)
        existing = self.repository.get_connection(merchant_id, "STRIPE")
        connection = ProviderConnection(
            id=existing.id if existing else _id("connection"),
            merchant_id=merchant_id,
            provider="STRIPE",
            status=ConnectionStatus.CONNECTED,
            provider_account_id=credentials.provider_account_id,
            token_expires_at=None,
            scope=credentials.scope,
            livemode=False,
            created_at=existing.created_at if existing else now,
            updated_at=now,
            last_sync_at=existing.last_sync_at if existing else None,
            transactions_imported=existing.transactions_imported if existing else 0,
            webhook_status="CONFIGURED" if self.webhook_secret else "NOT_CONFIGURED",
        )
        self.repository.save_connection(connection)
        self.credential_vault.save(connection.id, credentials.access_token, None)
        self._audit(merchant_id, "STRIPE_SANDBOX_CONNECTED", connection.id, actor_id=actor_id)
        return connection

    def complete_authorization(self, *, code: str, state: str) -> ProviderConnection:
        """Consume OAuth state, exchange code, encrypt tokens, and save connection."""
        connector = self._configured_connector()
        try:
            merchant_id = self.state_manager.consume(state)
        except ValueError as error:
            raise APIError(status_code=400, code="INVALID_OAUTH_STATE", message=str(error)) from error
        try:
            tokens = connector.exchange_authorization_code(code)
        except Exception as error:
            raise APIError(status_code=502, code="STRIPE_AUTHORIZATION_FAILED", message="Stripe did not accept the authorization code.") from error
        now = datetime.now(timezone.utc)
        existing = self.repository.get_connection(merchant_id, "STRIPE")
        connection = ProviderConnection(
            id=existing.id if existing else _id("connection"),
            merchant_id=merchant_id, provider="STRIPE", status=ConnectionStatus.CONNECTED,
            provider_account_id=tokens.provider_account_id, token_expires_at=tokens.expires_at,
            scope=tokens.scope, livemode=tokens.livemode,
            created_at=existing.created_at if existing else now, updated_at=now,
            last_sync_at=existing.last_sync_at if existing else None,
            transactions_imported=existing.transactions_imported if existing else 0,
            webhook_status="CONFIGURED" if self.webhook_secret else "NOT_CONFIGURED",
        )
        self.repository.save_connection(connection)
        self.credential_vault.save(connection.id, tokens.access_token, tokens.refresh_token)
        self._audit(merchant_id, "STRIPE_CONNECTED", connection.id)
        return connection

    def disconnect(self, merchant_id: str, *, actor_id: str | None = None) -> bool:
        """Attempt remote deauthorization but always remove local access."""
        connection = self.status(merchant_id)
        revoked = False
        if connection and connection.provider_account_id and self.connector is not None:
            try:
                revoked = self.connector.revoke(connection.provider_account_id)
            except Exception:
                revoked = False
        self.repository.delete_connection(merchant_id, "STRIPE")
        self._audit(merchant_id, "STRIPE_DISCONNECTED", connection.id if connection else "stripe",
                    actor_id=actor_id, metadata={"provider_revoked": revoked})
        return revoked

    def _credentials(self, connection: ProviderConnection) -> ProviderCredentials:
        """Load/decrypt credentials and refresh them before expiry when possible."""
        access_token, refresh_token = self.credential_vault.load(connection.id)
        if connection.token_expires_at and connection.token_expires_at <= datetime.now(timezone.utc) + timedelta(minutes=5):
            if not refresh_token:
                raise APIError(status_code=409, code="STRIPE_REAUTHORIZATION_REQUIRED", message="The Stripe connection must be authorized again.")
            tokens = self._configured_connector().refresh_credentials(refresh_token)
            connection = connection.model_copy(update={
                "token_expires_at": tokens.expires_at, "updated_at": datetime.now(timezone.utc),
                "provider_account_id": tokens.provider_account_id, "scope": tokens.scope,
            })
            self.repository.save_connection(connection)
            self.credential_vault.save(connection.id, tokens.access_token, tokens.refresh_token)
            self._audit(connection.merchant_id, "PROVIDER_CREDENTIAL_REFRESHED", connection.id)
            return ProviderCredentials(access_token=tokens.access_token, refresh_token=tokens.refresh_token, expires_at=tokens.expires_at)
        return ProviderCredentials(access_token=access_token, refresh_token=refresh_token, expires_at=connection.token_expires_at)

    def sync(self, merchant: AuthenticatedMerchant, *, resume_job_id: str | None = None) -> SyncJob:
        """Page through Stripe, preserve raw objects, normalize, and analyse them."""
        connector = self._configured_connector()
        connection = self.status(merchant.merchant_id)
        if connection is None or connection.status != ConnectionStatus.CONNECTED:
            raise APIError(status_code=409, code="STRIPE_NOT_CONNECTED", message="Connect Stripe before starting a sync.")
        if resume_job_id:
            previous = self.repository.get_sync_job(resume_job_id, merchant.merchant_id)
            if previous is None or previous.status not in {SyncStatus.PARTIAL, SyncStatus.FAILED}:
                raise APIError(status_code=409, code="SYNC_NOT_RESUMABLE", message="The requested sync job cannot be resumed.")
            job = previous.model_copy(update={"status": SyncStatus.RUNNING, "completed_at": None})
        else:
            job = SyncJob(id=_id("sync"), merchant_id=merchant.merchant_id, connection_id=connection.id, status=SyncStatus.RUNNING, started_at=datetime.now(timezone.utc))
        self.repository.save_sync_job(job)
        self._audit(merchant.merchant_id, "SYNC_STARTED", job.id, actor_id=merchant.actor_id)
        credentials = self._credentials(connection)
        cursor = job.cursor
        # Completed follow-up syncs request only recent Stripe objects. The
        # overlap prevents boundary races; canonical upserts make it idempotent.
        # Resumed partial jobs retain their exact cursor and original window.
        incremental_since = (
            connection.last_sync_at - timedelta(minutes=5)
            if not resume_job_id and connection.last_sync_at
            else None
        )
        try:
            while True:
                page = connector.sync_historical(
                    access_token=credentials.access_token,
                    starting_after=cursor,
                    created_after=incremental_since,
                )
                for payload in page.objects:
                    raw = self._raw(
                        merchant.merchant_id, "payment_intent", payload,
                        "INCREMENTAL_SYNC" if incremental_since else "HISTORICAL_SYNC",
                    )
                    raw_id = self.raw_store.put(raw)
                    transaction = self.normalizer.normalize(payload, merchant_id=merchant.merchant_id, raw_reference=raw_id, source=SourceType.API)
                    self.repository.upsert_canonical(transaction)
                    job = job.model_copy(update={
                        "records_received": job.records_received + 1,
                        "records_normalised": job.records_normalised + 1,
                    })
                cursor = page.next_cursor
                job = job.model_copy(update={"cursor": cursor})
                self.repository.save_sync_job(job)
                if not page.has_more:
                    break
            transactions = self.repository.list_canonical(merchant.merchant_id, "STRIPE")
            analysis = self.analysis_service.create_from_transactions(
                transactions, merchant, filename="stripe-payment-intents", source="STRIPE"
            )
            now = datetime.now(timezone.utc)
            job = job.model_copy(update={"status": SyncStatus.COMPLETED, "completed_at": now, "cursor": None, "analysis_id": analysis.analysis_id})
            self.repository.save_sync_job(job)
            self.repository.save_connection(connection.model_copy(update={
                "updated_at": now, "last_sync_at": now,
                "transactions_imported": len(transactions),
            }))
            self._audit(merchant.merchant_id, "SYNC_COMPLETED", job.id, actor_id=merchant.actor_id,
                        metadata={"records_normalised": job.records_normalised, "analysis_id": job.analysis_id,
                                  "sync_mode": "incremental" if incremental_since else "historical"})
            return job
        except APIError:
            raise
        except Exception as error:
            status = SyncStatus.PARTIAL if job.records_received else SyncStatus.FAILED
            job = job.model_copy(update={
                "status": status, "completed_at": datetime.now(timezone.utc),
                "cursor": cursor, "errors": [*job.errors, type(error).__name__],
            })
            self.repository.save_sync_job(job)
            self._audit(merchant.merchant_id, "SYNC_FAILED", job.id, actor_id=merchant.actor_id,
                        metadata={"error_type": type(error).__name__})
            return job

    def _raw(self, merchant_id: str, object_type: str, payload: dict, source: str) -> RawProviderObject:
        provider_id = payload.get("id") or hashlib.sha256(repr(sorted(payload)).encode()).hexdigest()
        raw_id = "raw_" + hashlib.sha256(f"{merchant_id}:STRIPE:{object_type}:{provider_id}".encode()).hexdigest()[:32]
        return RawProviderObject(
            id=raw_id, merchant_id=merchant_id, provider="STRIPE",
            provider_object_type=object_type, provider_object_id=str(provider_id),
            received_at=datetime.now(timezone.utc), source=source,
            schema_version=self.normalizer.schema_version, payload=payload,
        )

    def process_webhook(self, payload: bytes, signature: str) -> dict:
        """Verify a local-mode webhook then pass its trusted event onward."""
        if not self.webhook_secret:
            raise APIError(status_code=503, code="STRIPE_WEBHOOK_NOT_CONFIGURED", message="Stripe webhook verification is not configured.")
        try:
            event = self._configured_connector().verify_webhook(payload, signature, self.webhook_secret)
        except Exception as error:
            raise APIError(status_code=400, code="INVALID_WEBHOOK_SIGNATURE", message="The Stripe webhook signature is invalid.") from error
        accepted = self.accept_verified_webhook(event)
        if accepted["status"] == "duplicate":
            return {"status": "duplicate", "event_id": event["id"]}
        return self.process_verified_webhook(event, already_recorded=True)

    def accept_verified_webhook(self, event: dict) -> dict:
        """Preserve and deduplicate a signature-verified event before queueing."""
        account_id = event.get("account")
        if not account_id and self.connector is not None and self.connector.connection_mode == "SANDBOX_KEY":
            account_id = self.connector.sandbox_account_id
        connection = self.repository.find_connection_by_account("STRIPE", account_id or "")
        if connection is None:
            raise APIError(status_code=404, code="STRIPE_CONNECTION_NOT_FOUND", message="No merchant connection matches this Stripe event.")
        raw = self._raw(connection.merchant_id, "event", event, "WEBHOOK")
        raw_id = self.raw_store.put(raw)
        if not self.repository.record_webhook_event(event_id=event["id"], merchant_id=connection.merchant_id, event_type=event["type"], raw_object_id=raw_id):
            return {"status": "duplicate", "event_id": event["id"]}
        return {"status": "accepted", "event_id": event["id"], "merchant_id": connection.merchant_id}

    def process_verified_webhook(self, event: dict, *, already_recorded: bool = False) -> dict:
        """Normalize the event's transaction update after durable acceptance."""
        account_id = event.get("account")
        if not account_id and self.connector is not None and self.connector.connection_mode == "SANDBOX_KEY":
            account_id = self.connector.sandbox_account_id
        connection = self.repository.find_connection_by_account("STRIPE", account_id or "")
        if connection is None:
            raise APIError(status_code=404, code="STRIPE_CONNECTION_NOT_FOUND", message="No merchant connection matches this Stripe event.")
        if not already_recorded:
            accepted = self.accept_verified_webhook(event)
            if accepted["status"] == "duplicate":
                return accepted
        object_payload = event.get("data", {}).get("object", {})
        supported = {"payment_intent.succeeded", "payment_intent.payment_failed", "payment_intent.canceled", "payment_intent.processing"}
        if event["type"] in supported:
            transaction_raw = self._raw(connection.merchant_id, "payment_intent", object_payload, "WEBHOOK")
            transaction_raw_id = self.raw_store.put(transaction_raw)
            transaction = self.normalizer.normalize(object_payload, merchant_id=connection.merchant_id, raw_reference=transaction_raw_id, source=SourceType.WEBHOOK)
            self.repository.upsert_canonical(transaction)
            result = {"status": "processed", "event_id": event["id"]}
        elif event["type"] in {"charge.refunded", "charge.dispute.created", "charge.dispute.closed"}:
            credentials = self._credentials(connection)
            payment_intent_id = object_payload.get("payment_intent")
            charge = object_payload.get("charge")
            if not payment_intent_id and isinstance(charge, dict):
                payment_intent_id = charge.get("payment_intent")
            if not payment_intent_id and isinstance(charge, str):
                charge_payload = self._configured_connector().fetch_charge(
                    access_token=credentials.access_token, charge_id=charge
                )
                payment_intent_id = charge_payload.get("payment_intent")
            if not payment_intent_id:
                result = {"status": "ignored", "event_id": event["id"]}
            else:
                intent = self._configured_connector().fetch_transaction(access_token=credentials.access_token, transaction_id=payment_intent_id)
                intent_raw = self._raw(connection.merchant_id, "payment_intent", intent, "WEBHOOK_REFRESH")
                intent_raw_id = self.raw_store.put(intent_raw)
                self.repository.upsert_canonical(self.normalizer.normalize(intent, merchant_id=connection.merchant_id, raw_reference=intent_raw_id, source=SourceType.WEBHOOK))
                result = {"status": "processed", "event_id": event["id"]}
        else:
            result = {"status": "ignored", "event_id": event["id"]}
        # Receipt and processing are separate lifecycle points. A worker failure
        # deliberately leaves processed_at empty so diagnostics can surface it.
        self.repository.mark_webhook_processed(event["id"], connection.merchant_id)
        self._audit(connection.merchant_id, "STRIPE_WEBHOOK_PROCESSED", event["id"],
                    metadata={"event_type": event["type"], "outcome": result["status"]})
        return result

    def reconcile(self, merchant_id: str) -> ReconciliationResult:
        """Fetch provider truth and repair missing or changed canonical rows."""
        connector = self._configured_connector()
        connection = self.status(merchant_id)
        if connection is None:
            raise APIError(status_code=409, code="STRIPE_NOT_CONNECTED", message="Connect Stripe before reconciliation.")
        credentials = self._credentials(connection)
        provider_items: list[dict] = []
        cursor = None
        for _ in range(20):
            page = connector.sync_historical(access_token=credentials.access_token, starting_after=cursor, created_after=datetime.now(timezone.utc) - timedelta(days=30))
            provider_items.extend(page.objects)
            cursor = page.next_cursor
            if not page.has_more: break
        result = ReconciliationResult(checked=len(provider_items))
        seen: set[str] = set()
        for payload in provider_items:
            provider_id = payload["id"]
            if provider_id in seen:
                result.duplicates.append(provider_id)
                continue
            seen.add(provider_id)
            existing = self.repository.get_canonical(merchant_id, "STRIPE", provider_id)
            raw = self._raw(merchant_id, "payment_intent", payload, "RECONCILIATION")
            raw_id = self.raw_store.put(raw)
            current = self.normalizer.normalize(payload, merchant_id=merchant_id, raw_reference=raw_id, source=SourceType.API)
            if existing is None:
                result.missing.append(provider_id)
                self.repository.upsert_canonical(current)
                result.repaired += 1
            elif (existing.provider_status, existing.amount, existing.refund_amount, existing.dispute_amount) != (current.provider_status, current.amount, current.refund_amount, current.dispute_amount):
                result.updated.append(provider_id)
                self.repository.upsert_canonical(current)
                result.repaired += 1
        return result

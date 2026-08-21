"""SQLAlchemy provider persistence and JSONB raw-object storage."""

from __future__ import annotations

import secrets
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import PayLensTransaction
from app.persistence.database import (
    CanonicalTransactionRow,
    OAuthStateRow,
    ProviderConnectionRow,
    RawProviderObjectRow,
    SyncJobRow,
    WebhookEventRow,
    utcnow,
)
from app.providers.models import ConnectionStatus, ProviderConnection, RawProviderObject, SyncJob, SyncStatus
from app.providers.raw_storage import RawProviderDataStore
from app.providers.repository import ProviderRepository


def _aware(value):
    return value if value is None or value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _connection(row: ProviderConnectionRow) -> ProviderConnection:
    return ProviderConnection(
        id=row.id, merchant_id=row.merchant_id, provider=row.provider,
        status=ConnectionStatus(row.status), provider_account_id=row.provider_account_id,
        token_expires_at=_aware(row.token_expires_at), scope=row.scope, livemode=row.livemode,
        created_at=_aware(row.created_at), updated_at=_aware(row.updated_at),
        last_sync_at=_aware(row.last_sync_at), transactions_imported=row.transactions_imported,
        webhook_status=row.webhook_status,
    )


def _job(row: SyncJobRow) -> SyncJob:
    return SyncJob(
        id=row.id, merchant_id=row.merchant_id, connection_id=row.connection_id,
        status=SyncStatus(row.status), cursor=row.cursor, started_at=_aware(row.started_at),
        completed_at=_aware(row.completed_at), records_received=row.records_received,
        records_normalised=row.records_normalised, errors=row.errors, analysis_id=row.analysis_id,
    )


class SQLProviderRepository(ProviderRepository):
    def __init__(self, engine) -> None:
        self.engine = engine

    def save_connection(self, connection: ProviderConnection) -> None:
        with Session(self.engine) as session, session.begin():
            row = session.get(ProviderConnectionRow, connection.id)
            values = connection.model_dump(exclude={"id"})
            values["status"] = connection.status.value
            if row is None:
                session.add(ProviderConnectionRow(id=connection.id, **values))
            else:
                for key, value in values.items(): setattr(row, key, value)

    def get_connection(self, merchant_id: str, provider: str) -> ProviderConnection | None:
        with Session(self.engine) as session:
            row = session.scalar(select(ProviderConnectionRow).where(ProviderConnectionRow.merchant_id == merchant_id, ProviderConnectionRow.provider == provider))
            return _connection(row) if row else None

    def find_connection_by_account(self, provider: str, account_id: str) -> ProviderConnection | None:
        with Session(self.engine) as session:
            row = session.scalar(select(ProviderConnectionRow).where(ProviderConnectionRow.provider == provider, ProviderConnectionRow.provider_account_id == account_id))
            return _connection(row) if row else None

    def delete_connection(self, merchant_id: str, provider: str) -> None:
        with Session(self.engine) as session, session.begin():
            session.execute(delete(ProviderConnectionRow).where(ProviderConnectionRow.merchant_id == merchant_id, ProviderConnectionRow.provider == provider))

    def save_encrypted_credentials(self, connection_id: str, access_token: str, refresh_token: str | None) -> None:
        with Session(self.engine) as session, session.begin():
            row = session.get(ProviderConnectionRow, connection_id)
            if row is None: raise KeyError(connection_id)
            row.access_token_encrypted = access_token
            row.refresh_token_encrypted = refresh_token

    def get_encrypted_credentials(self, connection_id: str) -> tuple[str, str | None] | None:
        with Session(self.engine) as session:
            row = session.get(ProviderConnectionRow, connection_id)
            if row is None or row.access_token_encrypted is None: return None
            return row.access_token_encrypted, row.refresh_token_encrypted

    def save_sync_job(self, job: SyncJob) -> None:
        with Session(self.engine) as session, session.begin():
            row = session.get(SyncJobRow, job.id)
            values = job.model_dump(exclude={"id"})
            values["status"] = job.status.value
            if row is None: session.add(SyncJobRow(id=job.id, **values))
            else:
                for key, value in values.items(): setattr(row, key, value)

    def get_sync_job(self, job_id: str, merchant_id: str) -> SyncJob | None:
        with Session(self.engine) as session:
            row = session.scalar(select(SyncJobRow).where(SyncJobRow.id == job_id, SyncJobRow.merchant_id == merchant_id))
            return _job(row) if row else None

    def upsert_canonical(self, transaction: PayLensTransaction) -> bool:
        with Session(self.engine) as session, session.begin():
            row = session.scalar(select(CanonicalTransactionRow).where(
                CanonicalTransactionRow.merchant_id == transaction.merchant_id,
                CanonicalTransactionRow.provider == transaction.provider.value,
                CanonicalTransactionRow.provider_transaction_id == transaction.provider_transaction_id,
            ))
            payload = transaction.model_dump(mode="json")
            if row is None:
                session.add(CanonicalTransactionRow(
                    id=transaction.id, merchant_id=transaction.merchant_id, provider=transaction.provider.value,
                    provider_transaction_id=transaction.provider_transaction_id,
                    provider_updated_at=transaction.updated_at_internal, payload=payload,
                ))
                return True
            row.payload = payload
            row.provider_updated_at = transaction.updated_at_internal
            row.updated_at = utcnow()
            return False

    def get_canonical(self, merchant_id: str, provider: str, provider_transaction_id: str) -> PayLensTransaction | None:
        with Session(self.engine) as session:
            row = session.scalar(select(CanonicalTransactionRow).where(CanonicalTransactionRow.merchant_id == merchant_id, CanonicalTransactionRow.provider == provider, CanonicalTransactionRow.provider_transaction_id == provider_transaction_id))
            return PayLensTransaction.model_validate(row.payload) if row else None

    def list_canonical(self, merchant_id: str, provider: str) -> list[PayLensTransaction]:
        with Session(self.engine) as session:
            rows = session.scalars(select(CanonicalTransactionRow).where(CanonicalTransactionRow.merchant_id == merchant_id, CanonicalTransactionRow.provider == provider)).all()
            return [PayLensTransaction.model_validate(row.payload) for row in rows]

    def record_webhook_event(self, *, event_id: str, merchant_id: str, event_type: str, raw_object_id: str) -> bool:
        try:
            with Session(self.engine) as session, session.begin():
                session.add(WebhookEventRow(
                    id=f"webhook_{secrets.token_hex(12)}", provider="STRIPE", provider_event_id=event_id,
                    merchant_id=merchant_id, event_type=event_type, received_at=utcnow(),
                    processed_at=utcnow(), raw_object_id=raw_object_id,
                ))
            return True
        except IntegrityError:
            return False

    def store_oauth_state(self, nonce_hash: str, merchant_id: str, created_at: datetime, expires_at: datetime) -> None:
        with Session(self.engine) as session, session.begin():
            session.add(OAuthStateRow(nonce_hash=nonce_hash, merchant_id=merchant_id, created_at=created_at, expires_at=expires_at))

    def consume_oauth_state(self, nonce_hash: str, merchant_id: str) -> bool:
        with Session(self.engine) as session, session.begin():
            row = session.get(OAuthStateRow, nonce_hash)
            now = utcnow()
            if row is None or row.merchant_id != merchant_id or row.consumed_at is not None or _aware(row.expires_at) < now:
                return False
            row.consumed_at = now
            return True


class PostgreSQLRawProviderDataStore(RawProviderDataStore):
    def __init__(self, engine) -> None:
        self.engine = engine

    def put(self, item: RawProviderObject) -> str:
        with Session(self.engine) as session, session.begin():
            row = session.scalar(select(RawProviderObjectRow).where(
                RawProviderObjectRow.merchant_id == item.merchant_id,
                RawProviderObjectRow.provider == item.provider,
                RawProviderObjectRow.provider_object_type == item.provider_object_type,
                RawProviderObjectRow.provider_object_id == item.provider_object_id,
            ))
            values = item.model_dump(exclude={"id"})
            if row is None: session.add(RawProviderObjectRow(id=item.id, **values))
            else:
                for key, value in values.items(): setattr(row, key, value)
                item = item.model_copy(update={"id": row.id})
        return item.id

    def get(self, raw_id: str, merchant_id: str) -> RawProviderObject | None:
        with Session(self.engine) as session:
            row = session.scalar(select(RawProviderObjectRow).where(RawProviderObjectRow.id == raw_id, RawProviderObjectRow.merchant_id == merchant_id))
            if row is None: return None
            return RawProviderObject(
                id=row.id, merchant_id=row.merchant_id, provider=row.provider,
                provider_object_type=row.provider_object_type, provider_object_id=row.provider_object_id,
                received_at=_aware(row.received_at), source=row.source, schema_version=row.schema_version,
                payload=row.payload,
            )

"""Provider connection and synchronization persistence boundary."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from threading import RLock

from app.models import PayLensTransaction
from app.providers.models import ProviderConnection, SyncJob


class ProviderRepository(ABC):
    @abstractmethod
    def save_connection(self, connection: ProviderConnection) -> None: ...

    @abstractmethod
    def get_connection(self, merchant_id: str, provider: str) -> ProviderConnection | None: ...

    @abstractmethod
    def find_connection_by_account(self, provider: str, account_id: str) -> ProviderConnection | None: ...

    @abstractmethod
    def delete_connection(self, merchant_id: str, provider: str) -> None: ...

    @abstractmethod
    def save_encrypted_credentials(self, connection_id: str, access_token: str, refresh_token: str | None) -> None: ...

    @abstractmethod
    def get_encrypted_credentials(self, connection_id: str) -> tuple[str, str | None] | None: ...

    @abstractmethod
    def save_sync_job(self, job: SyncJob) -> None: ...

    @abstractmethod
    def get_sync_job(self, job_id: str, merchant_id: str) -> SyncJob | None: ...

    @abstractmethod
    def upsert_canonical(self, transaction: PayLensTransaction) -> bool: ...

    @abstractmethod
    def get_canonical(self, merchant_id: str, provider: str, provider_transaction_id: str) -> PayLensTransaction | None: ...

    @abstractmethod
    def list_canonical(self, merchant_id: str, provider: str) -> list[PayLensTransaction]: ...

    @abstractmethod
    def record_webhook_event(self, *, event_id: str, merchant_id: str, event_type: str, raw_object_id: str) -> bool: ...

    @abstractmethod
    def store_oauth_state(self, nonce_hash: str, merchant_id: str, created_at: datetime, expires_at: datetime) -> None: ...

    @abstractmethod
    def consume_oauth_state(self, nonce_hash: str, merchant_id: str) -> bool: ...


class InMemoryProviderRepository(ProviderRepository):
    def __init__(self) -> None:
        self.connections: dict[tuple[str, str], ProviderConnection] = {}
        self.credentials: dict[str, tuple[str, str | None]] = {}
        self.jobs: dict[str, SyncJob] = {}
        self.canonical: dict[tuple[str, str, str], PayLensTransaction] = {}
        self.webhook_events: set[str] = set()
        self.oauth_states: dict[str, tuple[str, datetime, datetime | None]] = {}
        self._lock = RLock()

    def save_connection(self, connection: ProviderConnection) -> None:
        with self._lock:
            self.connections[(connection.merchant_id, connection.provider)] = connection

    def get_connection(self, merchant_id: str, provider: str) -> ProviderConnection | None:
        with self._lock:
            return self.connections.get((merchant_id, provider))

    def find_connection_by_account(self, provider: str, account_id: str) -> ProviderConnection | None:
        with self._lock:
            return next((item for item in self.connections.values() if item.provider == provider and item.provider_account_id == account_id), None)

    def delete_connection(self, merchant_id: str, provider: str) -> None:
        with self._lock:
            item = self.connections.pop((merchant_id, provider), None)
            if item:
                self.credentials.pop(item.id, None)

    def save_encrypted_credentials(self, connection_id: str, access_token: str, refresh_token: str | None) -> None:
        with self._lock:
            self.credentials[connection_id] = (access_token, refresh_token)

    def get_encrypted_credentials(self, connection_id: str) -> tuple[str, str | None] | None:
        with self._lock:
            return self.credentials.get(connection_id)

    def save_sync_job(self, job: SyncJob) -> None:
        with self._lock:
            self.jobs[job.id] = job

    def get_sync_job(self, job_id: str, merchant_id: str) -> SyncJob | None:
        with self._lock:
            job = self.jobs.get(job_id)
        return job if job and job.merchant_id == merchant_id else None

    def upsert_canonical(self, transaction: PayLensTransaction) -> bool:
        key = (transaction.merchant_id, transaction.provider.value, transaction.provider_transaction_id)
        with self._lock:
            created = key not in self.canonical
            self.canonical[key] = transaction
        return created

    def get_canonical(self, merchant_id: str, provider: str, provider_transaction_id: str) -> PayLensTransaction | None:
        with self._lock:
            return self.canonical.get((merchant_id, provider, provider_transaction_id))

    def list_canonical(self, merchant_id: str, provider: str) -> list[PayLensTransaction]:
        with self._lock:
            return [item for (owner, item_provider, _), item in self.canonical.items() if owner == merchant_id and item_provider == provider]

    def record_webhook_event(self, *, event_id: str, merchant_id: str, event_type: str, raw_object_id: str) -> bool:
        with self._lock:
            if event_id in self.webhook_events:
                return False
            self.webhook_events.add(event_id)
            return True

    def store_oauth_state(self, nonce_hash: str, merchant_id: str, created_at: datetime, expires_at: datetime) -> None:
        with self._lock:
            self.oauth_states[nonce_hash] = (merchant_id, expires_at, None)

    def consume_oauth_state(self, nonce_hash: str, merchant_id: str) -> bool:
        now = datetime.now(timezone.utc)
        with self._lock:
            item = self.oauth_states.get(nonce_hash)
            if item is None or item[0] != merchant_id or item[1] < now or item[2] is not None:
                return False
            self.oauth_states[nonce_hash] = (item[0], item[1], now)
            return True

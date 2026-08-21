from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class ConnectionStatus(StrEnum):
    PENDING = "PENDING"
    CONNECTED = "CONNECTED"
    ERROR = "ERROR"
    DISCONNECTED = "DISCONNECTED"


class SyncStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"


class ProviderConnection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    merchant_id: str
    provider: str
    status: ConnectionStatus
    provider_account_id: str | None = None
    token_expires_at: datetime | None = None
    scope: str | None = None
    livemode: bool = False
    created_at: datetime
    updated_at: datetime
    last_sync_at: datetime | None = None
    transactions_imported: int = Field(default=0, ge=0)
    webhook_status: str = "NOT_CONFIGURED"


class ProviderCredentials(BaseModel):
    model_config = ConfigDict(extra="forbid")

    access_token: str
    refresh_token: str | None = None
    expires_at: datetime | None = None


class OAuthTokenResponse(ProviderCredentials):
    provider_account_id: str
    scope: str | None = None
    livemode: bool = False


class SyncJob(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    merchant_id: str
    connection_id: str
    status: SyncStatus
    cursor: str | None = None
    started_at: datetime
    completed_at: datetime | None = None
    records_received: int = Field(default=0, ge=0)
    records_normalised: int = Field(default=0, ge=0)
    errors: list[str] = Field(default_factory=list)
    analysis_id: str | None = None


class RawProviderObject(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    merchant_id: str
    provider: str
    provider_object_type: str
    provider_object_id: str
    received_at: datetime
    source: str
    schema_version: str
    payload: dict


class ProviderPage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    objects: list[dict]
    has_more: bool
    next_cursor: str | None = None


class ReconciliationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    checked: int = 0
    missing: list[str] = Field(default_factory=list)
    updated: list[str] = Field(default_factory=list)
    duplicates: list[str] = Field(default_factory=list)
    repaired: int = 0

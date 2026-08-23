"""SQLAlchemy schema shared by repositories and Alembic."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


JSON_DOCUMENT = JSON().with_variant(JSONB(), "postgresql")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class MerchantRow(Base):
    """Tenant root referenced by every merchant-owned table."""
    __tablename__ = "merchants"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class AnalysisRow(Base):
    """Analysis metadata and cached structured result documents."""
    __tablename__ = "analyses"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    merchant_id: Mapped[str] = mapped_column(ForeignKey("merchants.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    source: Mapped[str] = mapped_column(String(24), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    current_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    current_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    performance: Mapped[dict] = mapped_column(JSON_DOCUMENT, nullable=False)
    timings: Mapped[dict] = mapped_column(JSON_DOCUMENT, nullable=False)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON_DOCUMENT, default=dict, nullable=False)


class AnalysisInsightRow(Base):
    __tablename__ = "analysis_insights"

    insight_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    analysis_id: Mapped[str] = mapped_column(ForeignKey("analyses.id", ondelete="CASCADE"), primary_key=True)
    merchant_id: Mapped[str] = mapped_column(ForeignKey("merchants.id", ondelete="CASCADE"), index=True)
    payload: Mapped[dict] = mapped_column(JSON_DOCUMENT, nullable=False)


class CanonicalTransactionRow(Base):
    """Canonical payload uniquely identified inside a merchant/provider pair."""
    __tablename__ = "canonical_transactions"
    __table_args__ = (
        UniqueConstraint("merchant_id", "provider", "provider_transaction_id", name="uq_canonical_provider_transaction"),
        Index("ix_canonical_analysis", "analysis_id"),
    )

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    merchant_id: Mapped[str] = mapped_column(ForeignKey("merchants.id", ondelete="CASCADE"), index=True)
    analysis_id: Mapped[str | None] = mapped_column(ForeignKey("analyses.id", ondelete="SET NULL"), nullable=True)
    provider: Mapped[str] = mapped_column(String(24), nullable=False)
    provider_transaction_id: Mapped[str] = mapped_column(String(255), nullable=False)
    provider_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict] = mapped_column(JSON_DOCUMENT, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class ProviderConnectionRow(Base):
    """Provider account metadata plus encrypted credential ciphertext."""
    __tablename__ = "provider_connections"
    __table_args__ = (UniqueConstraint("merchant_id", "provider", name="uq_merchant_provider_connection"),)

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    merchant_id: Mapped[str] = mapped_column(ForeignKey("merchants.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(24), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    provider_account_id: Mapped[str | None] = mapped_column(String(255), index=True)
    access_token_encrypted: Mapped[str | None] = mapped_column(Text)
    refresh_token_encrypted: Mapped[str | None] = mapped_column(Text)
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scope: Mapped[str | None] = mapped_column(String(100))
    livemode: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    transactions_imported: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    webhook_status: Mapped[str] = mapped_column(String(24), default="NOT_CONFIGURED", nullable=False)


class SyncJobRow(Base):
    __tablename__ = "sync_jobs"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    merchant_id: Mapped[str] = mapped_column(ForeignKey("merchants.id", ondelete="CASCADE"), index=True)
    connection_id: Mapped[str] = mapped_column(ForeignKey("provider_connections.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    cursor: Mapped[str | None] = mapped_column(String(255))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    records_received: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    records_normalised: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    errors: Mapped[list] = mapped_column(JSON_DOCUMENT, default=list, nullable=False)
    analysis_id: Mapped[str | None] = mapped_column(ForeignKey("analyses.id", ondelete="SET NULL"))


class RawProviderObjectRow(Base):
    __tablename__ = "raw_provider_objects"
    __table_args__ = (
        UniqueConstraint("merchant_id", "provider", "provider_object_type", "provider_object_id", name="uq_raw_provider_object"),
    )

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    merchant_id: Mapped[str] = mapped_column(ForeignKey("merchants.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(24), nullable=False)
    provider_object_type: Mapped[str] = mapped_column(String(100), nullable=False)
    provider_object_id: Mapped[str] = mapped_column(String(255), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source: Mapped[str] = mapped_column(String(24), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(100), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON_DOCUMENT, nullable=False)


class WebhookEventRow(Base):
    """Unique provider event ledger enforcing webhook idempotency."""
    __tablename__ = "webhook_events"
    __table_args__ = (UniqueConstraint("provider", "provider_event_id", name="uq_provider_webhook_event"),)

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    provider: Mapped[str] = mapped_column(String(24), nullable=False)
    provider_event_id: Mapped[str] = mapped_column(String(255), nullable=False)
    merchant_id: Mapped[str] = mapped_column(ForeignKey("merchants.id", ondelete="CASCADE"), index=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # May be a PostgreSQL raw ID locally or an encrypted S3 URI in AWS.
    raw_object_id: Mapped[str] = mapped_column(String(1024), nullable=False)


class OAuthStateRow(Base):
    __tablename__ = "oauth_states"

    nonce_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    merchant_id: Mapped[str] = mapped_column(ForeignKey("merchants.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class UserRow(Base):
    __tablename__ = "users"

    subject: Mapped[str] = mapped_column(String(128), primary_key=True)
    email: Mapped[str | None] = mapped_column(String(320), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class MerchantMembershipRow(Base):
    """User-to-merchant authorization relationship and role."""
    __tablename__ = "merchant_memberships"

    merchant_id: Mapped[str] = mapped_column(ForeignKey("merchants.id", ondelete="CASCADE"), primary_key=True)
    user_subject: Mapped[str] = mapped_column(ForeignKey("users.subject", ondelete="CASCADE"), primary_key=True)
    role: Mapped[str] = mapped_column(String(24), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class AsyncJobRow(Base):
    """Durable job state with merchant-scoped deduplication."""
    __tablename__ = "async_jobs"
    __table_args__ = (UniqueConstraint("merchant_id", "deduplication_key", name="uq_async_job_deduplication"),)

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    merchant_id: Mapped[str] = mapped_column(ForeignKey("merchants.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    deduplication_key: Mapped[str] = mapped_column(String(255), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON_DOCUMENT, default=dict, nullable=False)
    result: Mapped[dict] = mapped_column(JSON_DOCUMENT, default=dict, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(100))
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AuditEventRow(Base):
    """Security/product event containing explicitly safe metadata only."""
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    merchant_id: Mapped[str] = mapped_column(ForeignKey("merchants.id", ondelete="CASCADE"), index=True)
    actor_id: Mapped[str | None] = mapped_column(String(128))
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource: Mapped[str] = mapped_column(String(255), nullable=False)
    safe_metadata: Mapped[dict] = mapped_column(JSON_DOCUMENT, default=dict, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


def create_engine_from_url(database_url: str):
    """Create the shared SQLAlchemy engine with stale-connection detection."""
    return create_engine(database_url, pool_pre_ping=True)

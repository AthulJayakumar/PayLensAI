"""add pilot identity jobs and audit

Revision ID: b5f500000001
Revises: aa4e231fa1b0
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "b5f500000001"
down_revision = "aa4e231fa1b0"
branch_labels = None
depends_on = None
json_document = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.drop_constraint("webhook_events_raw_object_id_fkey", "webhook_events", type_="foreignkey")
    op.alter_column("webhook_events", "raw_object_id", type_=sa.String(1024), existing_type=sa.String(100), existing_nullable=False)
    op.create_table("users", sa.Column("subject", sa.String(128), primary_key=True), sa.Column("email", sa.String(320), unique=True), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("merchant_memberships", sa.Column("merchant_id", sa.String(64), sa.ForeignKey("merchants.id", ondelete="CASCADE"), primary_key=True), sa.Column("user_subject", sa.String(128), sa.ForeignKey("users.subject", ondelete="CASCADE"), primary_key=True), sa.Column("role", sa.String(24), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("async_jobs", sa.Column("id", sa.String(100), primary_key=True), sa.Column("merchant_id", sa.String(64), sa.ForeignKey("merchants.id", ondelete="CASCADE"), nullable=False), sa.Column("type", sa.String(32), nullable=False), sa.Column("status", sa.String(24), nullable=False), sa.Column("deduplication_key", sa.String(255), nullable=False), sa.Column("payload", json_document, nullable=False), sa.Column("result", json_document, nullable=False), sa.Column("error_code", sa.String(100)), sa.Column("attempts", sa.Integer(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False), sa.UniqueConstraint("merchant_id", "deduplication_key", name="uq_async_job_deduplication"))
    op.create_index("ix_async_jobs_merchant_id", "async_jobs", ["merchant_id"])
    op.create_table("audit_events", sa.Column("id", sa.String(100), primary_key=True), sa.Column("merchant_id", sa.String(64), sa.ForeignKey("merchants.id", ondelete="CASCADE"), nullable=False), sa.Column("actor_id", sa.String(128)), sa.Column("event_type", sa.String(64), nullable=False), sa.Column("resource", sa.String(255), nullable=False), sa.Column("safe_metadata", json_document, nullable=False), sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_audit_events_merchant_id", "audit_events", ["merchant_id"])


def downgrade() -> None:
    op.drop_table("audit_events")
    op.drop_table("async_jobs")
    op.drop_table("merchant_memberships")
    op.drop_table("users")
    op.alter_column("webhook_events", "raw_object_id", type_=sa.String(100), existing_type=sa.String(1024), existing_nullable=False)
    op.create_foreign_key("webhook_events_raw_object_id_fkey", "webhook_events", "raw_provider_objects", ["raw_object_id"], ["id"], ondelete="RESTRICT")

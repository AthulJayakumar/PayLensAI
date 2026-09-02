"""Persistence for identities, asynchronous jobs, and security audit events."""

from __future__ import annotations

import secrets
from datetime import datetime, timezone
from threading import RLock

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.auth import MerchantRole
from app.persistence.database import AsyncJobRow, AuditEventRow, MerchantMembershipRow, MerchantRow, UserRow
from app.providers.models import AsyncJob, JobStatus, JobType


class AuditEvent(BaseModel):
    """Safe audit contract that deliberately excludes tokens/payment payloads."""
    model_config = ConfigDict(extra="forbid")
    id: str = Field(default_factory=lambda: f"audit_{secrets.token_hex(12)}")
    merchant_id: str
    actor_id: str | None = None
    event_type: str
    resource: str
    safe_metadata: dict = Field(default_factory=dict)
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class InMemoryPilotRepository:
    """Thread-safe identity/job/audit adapter for deterministic tests."""
    def __init__(self) -> None:
        self.memberships: dict[str, tuple[str, str, MerchantRole]] = {}
        self.jobs: dict[str, AsyncJob] = {}
        self.dedupe: dict[tuple[str, str], str] = {}
        self.audit_events: list[AuditEvent] = []
        self._lock = RLock()

    def membership_for_subject(self, subject: str):
        return self.memberships.get(subject)

    def add_membership(self, subject: str, merchant_id: str, merchant_name: str, role: MerchantRole) -> None:
        self.memberships[subject] = (merchant_id, merchant_name, role)

    def create_job(self, job: AsyncJob) -> tuple[AsyncJob, bool]:
        with self._lock:
            existing_id = self.dedupe.get((job.merchant_id, job.deduplication_key))
            if existing_id:
                return self.jobs[existing_id], False
            self.jobs[job.id] = job
            self.dedupe[(job.merchant_id, job.deduplication_key)] = job.id
            return job, True

    def save_job(self, job: AsyncJob) -> None:
        with self._lock:
            self.jobs[job.id] = job

    def get_job(self, job_id: str, merchant_id: str) -> AsyncJob | None:
        job = self.jobs.get(job_id)
        return job if job and job.merchant_id == merchant_id else None

    def list_jobs(self, merchant_id: str, *, limit: int = 10) -> list[AsyncJob]:
        jobs = [item for item in self.jobs.values() if item.merchant_id == merchant_id]
        return sorted(jobs, key=lambda item: item.created_at, reverse=True)[:limit]

    def record(self, event: AuditEvent) -> None:
        self.audit_events.append(event)


class SQLPilotRepository:
    """Persistent memberships, jobs, deduplication, and audit events."""
    def __init__(self, engine) -> None:
        self.engine = engine

    def membership_for_subject(self, subject: str):
        with Session(self.engine) as session:
            row = session.execute(
                select(MerchantMembershipRow, MerchantRow)
                .join(MerchantRow, MerchantRow.id == MerchantMembershipRow.merchant_id)
                .where(MerchantMembershipRow.user_subject == subject)
            ).first()
            return (row[0].merchant_id, row[1].name, MerchantRole(row[0].role)) if row else None

    def add_membership(self, subject: str, merchant_id: str, merchant_name: str, role: MerchantRole, email: str | None = None) -> None:
        with Session(self.engine) as session, session.begin():
            if session.get(MerchantRow, merchant_id) is None:
                session.add(MerchantRow(id=merchant_id, name=merchant_name))
            if session.get(UserRow, subject) is None:
                session.add(UserRow(subject=subject, email=email))
            session.merge(MerchantMembershipRow(merchant_id=merchant_id, user_subject=subject, role=role.value))

    @staticmethod
    def _job(row: AsyncJobRow) -> AsyncJob:
        return AsyncJob(id=row.id, merchant_id=row.merchant_id, type=JobType(row.type), status=JobStatus(row.status),
                        deduplication_key=row.deduplication_key, payload=row.payload, result=row.result,
                        error_code=row.error_code, attempts=row.attempts, created_at=row.created_at, updated_at=row.updated_at)

    def create_job(self, job: AsyncJob) -> tuple[AsyncJob, bool]:
        """Let PostgreSQL's unique key arbitrate concurrent duplicate requests."""
        try:
            with Session(self.engine) as session, session.begin():
                session.add(AsyncJobRow(**job.model_dump(mode="python", exclude={"type", "status"}), type=job.type.value, status=job.status.value))
            return job, True
        except IntegrityError:
            with Session(self.engine) as session:
                row = session.scalar(select(AsyncJobRow).where(AsyncJobRow.merchant_id == job.merchant_id,
                    AsyncJobRow.deduplication_key == job.deduplication_key))
                return self._job(row), False

    def save_job(self, job: AsyncJob) -> None:
        with Session(self.engine) as session, session.begin():
            row = session.get(AsyncJobRow, job.id)
            if row is None:
                raise KeyError(job.id)
            for key, value in job.model_dump(exclude={"id", "type", "status"}).items():
                setattr(row, key, value)
            row.type, row.status = job.type.value, job.status.value

    def get_job(self, job_id: str, merchant_id: str) -> AsyncJob | None:
        with Session(self.engine) as session:
            row = session.scalar(select(AsyncJobRow).where(AsyncJobRow.id == job_id, AsyncJobRow.merchant_id == merchant_id))
            return self._job(row) if row else None

    def list_jobs(self, merchant_id: str, *, limit: int = 10) -> list[AsyncJob]:
        with Session(self.engine) as session:
            rows = session.scalars(
                select(AsyncJobRow)
                .where(AsyncJobRow.merchant_id == merchant_id)
                .order_by(AsyncJobRow.created_at.desc())
                .limit(limit)
            ).all()
            return [self._job(row) for row in rows]

    def record(self, event: AuditEvent) -> None:
        with Session(self.engine) as session, session.begin():
            session.add(AuditEventRow(**event.model_dump()))

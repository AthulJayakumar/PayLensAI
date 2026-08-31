"""Tests for the production-packaged merchant provisioning command."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.admin import provision_user
from app.api.auth import MerchantRole
from app.persistence.database import (
    Base,
    MerchantMembershipRow,
    MerchantRow,
    UserRow,
    database_url_from_environment,
)
from app.persistence.pilot_repository import SQLPilotRepository


def sqlite_engine():
    """Create an isolated relational store for provisioning behavior."""

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


def test_provision_membership_is_idempotent() -> None:
    engine = sqlite_engine()

    for _ in range(2):
        provision_user.provision_membership(
            subject="cognito-subject-1",
            email="owner@example.com",
            merchant_id="merchant-pilot",
            merchant_name="Pilot Merchant",
            role=MerchantRole.OWNER,
            engine=engine,
        )

    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(UserRow)) == 1
        assert session.scalar(select(func.count()).select_from(MerchantRow)) == 1
        assert session.scalar(select(func.count()).select_from(MerchantMembershipRow)) == 1
    assert _sql_membership(engine) == (
        "merchant-pilot",
        "Pilot Merchant",
        MerchantRole.OWNER,
    )


def _sql_membership(engine):
    """Read the provisioned authorization through the production repository."""

    return SQLPilotRepository(engine).membership_for_subject("cognito-subject-1")


def test_provisioning_requires_secret_injected_database_configuration(monkeypatch) -> None:
    for name in ("DATABASE_URL", "DB_HOST", "DB_USERNAME", "DB_PASSWORD"):
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(RuntimeError, match="Database configuration is required"):
        provision_user.provision_membership(
            subject="subject",
            email="owner@example.com",
            merchant_id="merchant",
            merchant_name="Merchant",
            role=MerchantRole.OWNER,
        )


def test_database_url_uses_and_escapes_secret_injected_values(monkeypatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("DB_HOST", "database.internal")
    monkeypatch.setenv("DB_USERNAME", "merchant@app")
    monkeypatch.setenv("DB_PASSWORD", "secret:/value")
    monkeypatch.setenv("DB_PORT", "5433")
    monkeypatch.setenv("DB_NAME", "paylens_pilot")

    assert database_url_from_environment() == (
        "postgresql+psycopg://merchant%40app:secret%3A%2Fvalue@"
        "database.internal:5433/paylens_pilot?sslmode=require"
    )


def test_cli_rejects_an_invalid_role() -> None:
    with pytest.raises(SystemExit) as error:
        provision_user.build_parser().parse_args(
            [
                "--subject", "subject",
                "--email", "owner@example.com",
                "--merchant-id", "merchant",
                "--merchant-name", "Merchant",
                "--role", "SUPERUSER",
            ]
        )

    assert error.value.code == 2


def test_cli_prints_no_identity_or_database_details(monkeypatch, capsys) -> None:
    captured = {}
    monkeypatch.setattr(
        provision_user,
        "provision_membership",
        lambda **values: captured.update(values),
    )

    result = provision_user.main(
        [
            "--subject", "private-subject",
            "--email", "private@example.com",
            "--merchant-id", "merchant-private",
            "--merchant-name", "Private Merchant",
        ]
    )

    output = capsys.readouterr().out
    assert result == 0
    assert output == "Merchant membership provisioned.\n"
    assert "private-subject" not in output
    assert "private@example.com" not in output
    assert captured["role"] == MerchantRole.OWNER

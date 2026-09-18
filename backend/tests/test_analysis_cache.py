"""Tests for the bounded cache that accelerates repeated dashboard reads."""

from decimal import Decimal

from sqlalchemy import create_engine, event, select

from app.api.auth import AuthenticatedMerchant
from app.api.services.analysis import AnalysisService
from app.persistence.analysis_repository import PostgreSQLAnalysisRepository
from app.persistence.database import Base, CanonicalTransactionRow


def test_postgresql_repository_reuses_a_hydrated_analysis(transaction_factory, monkeypatch) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    writer = PostgreSQLAnalysisRepository(engine, cache_ttl_seconds=60, cache_max_entries=2)
    merchant = AuthenticatedMerchant(merchant_id="merchant_cache", name="Cache Merchant")
    record = AnalysisService(writer).create_from_transactions(
        [transaction_factory(merchant_id=merchant.merchant_id)],
        merchant,
        filename="cache-test",
        source="STRIPE",
    )

    # A new repository simulates the API process reading a worker-created analysis.
    reader = PostgreSQLAnalysisRepository(engine, cache_ttl_seconds=60, cache_max_entries=2)
    original_load = reader._load_record
    database_loads = 0

    def counted_load(analysis_id: str):
        nonlocal database_loads
        database_loads += 1
        return original_load(analysis_id)

    monkeypatch.setattr(reader, "_load_record", counted_load)
    first = reader.get_for_merchant(record.analysis_id, merchant.merchant_id)
    second = reader.get_for_merchant(record.analysis_id, merchant.merchant_id)

    assert first is not None and second is first
    assert database_loads == 1
    assert reader.get_for_merchant(record.analysis_id, "merchant_other") is None


def test_analysis_cache_can_be_disabled(transaction_factory, monkeypatch) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    repository = PostgreSQLAnalysisRepository(engine, cache_ttl_seconds=0)
    merchant = AuthenticatedMerchant(merchant_id="merchant_no_cache", name="No Cache Merchant")
    record = AnalysisService(repository).create_from_transactions(
        [transaction_factory(merchant_id=merchant.merchant_id)],
        merchant,
        filename="no-cache-test",
        source="STRIPE",
    )
    original_load = repository._load_record
    database_loads = 0

    def counted_load(analysis_id: str):
        nonlocal database_loads
        database_loads += 1
        return original_load(analysis_id)

    monkeypatch.setattr(repository, "_load_record", counted_load)
    assert repository.get(record.analysis_id) is not None
    assert repository.get(record.analysis_id) is not None
    assert database_loads == 2


def test_analysis_save_batches_canonical_upserts_and_preserves_provider_identity(transaction_factory) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    repository = PostgreSQLAnalysisRepository(engine)
    merchant = AuthenticatedMerchant(merchant_id="merchant_bulk", name="Bulk Merchant")
    transactions = [transaction_factory(merchant_id=merchant.merchant_id) for _ in range(205)]
    canonical_writes = 0

    def count_canonical_writes(_connection, _cursor, statement, _parameters, _context, _executemany):
        nonlocal canonical_writes
        if statement.lstrip().upper().startswith("INSERT INTO CANONICAL_TRANSACTIONS"):
            canonical_writes += 1

    event.listen(engine, "before_cursor_execute", count_canonical_writes)
    try:
        AnalysisService(repository).create_from_transactions(
            transactions, merchant, filename="bulk-test", source="STRIPE"
        )
    finally:
        event.remove(engine, "before_cursor_execute", count_canonical_writes)

    assert canonical_writes == 3  # 100 + 100 + 5; never one query per payment.

    # Re-importing the same provider identity updates its payload, not its row ID.
    updated = transactions[0].model_copy(update={
        "amount": Decimal("125"), "gross_amount": Decimal("125")
    })
    AnalysisService(repository).create_from_transactions(
        [updated], merchant, filename="repeat-test", source="STRIPE"
    )
    with engine.connect() as connection:
        rows = connection.execute(select(CanonicalTransactionRow).where(
            CanonicalTransactionRow.merchant_id == merchant.merchant_id
        )).all()
    assert len(rows) == 205
    assert any(str(row.payload["amount"]) == "125" for row in rows)

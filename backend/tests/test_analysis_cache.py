"""Tests for the bounded cache that accelerates repeated dashboard reads."""

from sqlalchemy import create_engine

from app.api.auth import AuthenticatedMerchant
from app.api.services.analysis import AnalysisService
from app.persistence.analysis_repository import PostgreSQLAnalysisRepository
from app.persistence.database import Base


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

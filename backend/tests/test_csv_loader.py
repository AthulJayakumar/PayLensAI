import pytest

from app.analytics.csv_loader import CSVTransactionValidationError, load_transactions_csv
from app.synthetic.config import GenerationConfig
from app.synthetic.csv_export import export_transactions_csv
from app.synthetic.generator import generate_transactions


def test_exported_canonical_csv_round_trips(tmp_path) -> None:
    destination = tmp_path / "canonical.csv"
    original = list(generate_transactions(GenerationConfig(count=20, seed=81)))
    export_transactions_csv(original, destination)
    loaded = load_transactions_csv(destination)
    assert loaded == original


def test_missing_canonical_columns_are_rejected(tmp_path) -> None:
    destination = tmp_path / "invalid.csv"
    destination.write_text("id,merchant_id\n1,m1\n", encoding="utf-8")
    with pytest.raises(CSVTransactionValidationError, match="missing canonical fields"):
        load_transactions_csv(destination)


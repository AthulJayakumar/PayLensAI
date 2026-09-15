import csv

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


def test_historical_csv_without_new_optional_settlement_fields_still_loads(tmp_path) -> None:
    current = tmp_path / "current.csv"
    historical = tmp_path / "historical.csv"
    original = list(generate_transactions(GenerationConfig(count=2, seed=92)))
    export_transactions_csv(original, current)
    omitted = {"settlement_gross_amount", "settlement_fee", "settlement_net_amount", "exchange_rate"}

    with current.open(newline="", encoding="utf-8") as source:
        rows = list(csv.DictReader(source))
        fieldnames = [name for name in rows[0] if name not in omitted]
    with historical.open("w", newline="", encoding="utf-8") as destination:
        writer = csv.DictWriter(destination, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows({key: value for key, value in row.items() if key in fieldnames} for row in rows)

    assert load_transactions_csv(historical) == original

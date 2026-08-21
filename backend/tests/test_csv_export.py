import csv

from app.synthetic.config import GenerationConfig
from app.synthetic.csv_export import export_transactions_csv
from app.synthetic.generator import generate_transactions


def test_csv_export_has_header_and_exact_row_count(tmp_path) -> None:
    destination = tmp_path / "transactions.csv"
    written = export_transactions_csv(
        generate_transactions(GenerationConfig(count=25, seed=5)), destination
    )
    with destination.open(newline="", encoding="utf-8") as source:
        rows = list(csv.DictReader(source))
    assert written == 25
    assert len(rows) == 25
    assert rows[0]["id"].startswith("ptx_")
    assert rows[0]["amount"]
    assert rows[0]["provider"] in {"STRIPE", "PAYPAL", "ADYEN"}


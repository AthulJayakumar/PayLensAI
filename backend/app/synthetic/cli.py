"""Command-line entry point for synthetic CSV generation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from pydantic import TypeAdapter

from app.synthetic.config import AnomalyRule, GenerationConfig, default_anomalies
from app.synthetic.csv_export import export_transactions_csv
from app.synthetic.generator import generate_transactions


def build_parser() -> argparse.ArgumentParser:
    """Describe the supported synthetic-data command-line arguments."""

    parser = argparse.ArgumentParser(description="Generate deterministic PayLens CSV data.")
    parser.add_argument("--count", type=int, default=100_000, help="Number of rows to generate.")
    parser.add_argument("--seed", type=int, default=20_260_822, help="Deterministic random seed.")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("synthetic-data/paylens-transactions.csv"),
        help="Destination CSV path.",
    )
    anomaly_group = parser.add_mutually_exclusive_group()
    anomaly_group.add_argument(
        "--anomaly-config", type=Path, help="JSON array of anomaly rule objects."
    )
    anomaly_group.add_argument(
        "--no-anomalies", action="store_true", help="Generate only baseline behaviour."
    )
    return parser


def _load_anomalies(path: Path) -> list[AnomalyRule]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return TypeAdapter(list[AnomalyRule]).validate_python(payload)


def main() -> None:
    """Generate a deterministic canonical CSV from command-line options."""

    args = build_parser().parse_args()
    if args.no_anomalies:
        anomalies: list[AnomalyRule] = []
    elif args.anomaly_config:
        anomalies = _load_anomalies(args.anomaly_config)
    else:
        anomalies = default_anomalies()

    config = GenerationConfig(count=args.count, seed=args.seed, anomalies=anomalies)
    written = export_transactions_csv(generate_transactions(config), args.output)
    print(f"Generated {written:,} transactions at {args.output.resolve()}")


if __name__ == "__main__":
    main()

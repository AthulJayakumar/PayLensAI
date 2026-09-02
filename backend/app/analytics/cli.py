"""Command-line interface for deterministic PayLens analysis."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from app.analytics.pipeline import analyse_csv


def _aware_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise argparse.ArgumentTypeError("timestamp must include a timezone")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    """Describe the supported command-line arguments for CSV analysis."""

    parser = argparse.ArgumentParser(description="Analyse canonical PayLens transaction CSV data.")
    parser.add_argument("--input", type=Path, required=True, help="Canonical PayLens CSV path.")
    parser.add_argument(
        "--current-start",
        type=_aware_datetime,
        required=True,
        help="Start of the current comparison period, including timezone.",
    )
    parser.add_argument(
        "--current-end",
        type=_aware_datetime,
        help="Optional exclusive end of the current comparison period.",
    )
    parser.add_argument("--output", type=Path, help="Optional structured JSON result path.")
    return parser


def main() -> None:
    """Run one CSV analysis and print its structured JSON result."""

    args = build_parser().parse_args()
    result = analyse_csv(
        args.input, current_start=args.current_start, current_end=args.current_end
    )
    payload = result.model_dump_json(indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
        print(f"Analysed {result.transaction_count:,} transactions; wrote {args.output.resolve()}")
        print(f"Detected {len(result.insights):,} structured insights")
        print(result.timings.model_dump_json())
    else:
        print(payload)


if __name__ == "__main__":
    main()

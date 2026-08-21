"""Atomic streaming CSV export for canonical transactions."""

from __future__ import annotations

import csv
import json
import os
from collections.abc import Iterable
from datetime import datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path

from app.models import PayLensTransaction


CSV_FIELDS = list(PayLensTransaction.model_fields)


def _csv_value(value: object) -> str | int | float | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return json.dumps(
            {key: item.value if isinstance(item, Enum) else item for key, item in value.items()},
            sort_keys=True,
            separators=(",", ":"),
        )
    return value


def export_transactions_csv(
    transactions: Iterable[PayLensTransaction], output_path: str | Path
) -> int:
    """Write validated records atomically and return the number written."""

    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    count = 0
    try:
        with temporary.open("w", newline="", encoding="utf-8") as output:
            writer = csv.DictWriter(output, fieldnames=CSV_FIELDS, extrasaction="raise")
            writer.writeheader()
            for transaction in transactions:
                row = transaction.model_dump(mode="python")
                writer.writerow({key: _csv_value(value) for key, value in row.items()})
                count += 1
        os.replace(temporary, destination)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return count


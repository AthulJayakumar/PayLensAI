"""Validated streaming loader for Sprint 1 canonical CSV exports."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from pydantic import ValidationError

from app.models import PayLensTransaction


class CSVTransactionValidationError(ValueError):
    """A canonical CSV row could not be validated."""


OPTIONAL_FIELDS = {
    field_name
    for field_name, field in PayLensTransaction.model_fields.items()
    if not field.is_required()
}


def load_transactions_csv(path: str | Path) -> list[PayLensTransaction]:
    """Load and validate a canonical PayLens CSV file."""

    transactions: list[PayLensTransaction] = []
    with Path(path).open(newline="", encoding="utf-8") as source:
        reader = csv.DictReader(source)
        missing = set(PayLensTransaction.model_fields) - set(reader.fieldnames or [])
        if missing:
            raise CSVTransactionValidationError(
                f"CSV is missing canonical fields: {', '.join(sorted(missing))}"
            )
        for row_number, row in enumerate(reader, start=2):
            payload: dict[str, object] = dict(row)
            for field in OPTIONAL_FIELDS:
                if payload.get(field) == "":
                    payload[field] = None
            try:
                payload["data_availability"] = json.loads(str(payload["data_availability"]))
                transactions.append(PayLensTransaction.model_validate(payload))
            except (ValidationError, json.JSONDecodeError) as error:
                raise CSVTransactionValidationError(
                    f"invalid canonical transaction at CSV row {row_number}: {error}"
                ) from error
    return transactions


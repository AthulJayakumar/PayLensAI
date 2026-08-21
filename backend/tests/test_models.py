from datetime import datetime, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.models import (
    PaymentMethod,
    PaymentProvider,
    PaymentStatus,
    PayLensTransaction,
    SourceType,
)


def valid_transaction_data() -> dict:
    now = datetime(2026, 6, 1, tzinfo=timezone.utc)
    return {
        "id": "ptx_test",
        "merchant_id": "merchant_test",
        "provider": PaymentProvider.STRIPE,
        "provider_transaction_id": "pi_test",
        "transaction_created_at": now,
        "authorised_at": now,
        "amount": Decimal("10.00"),
        "currency": "GBP",
        "status": PaymentStatus.SUCCEEDED,
        "provider_status": "succeeded",
        "payment_method": PaymentMethod.CARD,
        "gross_amount": Decimal("10.00"),
        "processing_fee": Decimal("0.10"),
        "provider_fee": Decimal("0.05"),
        "other_cost": Decimal("0.00"),
        "net_amount": Decimal("9.85"),
        "source_type": SourceType.CSV,
        "source_timestamp": now,
        "created_at_internal": now,
        "updated_at_internal": now,
    }


def test_valid_transaction_is_accepted() -> None:
    transaction = PayLensTransaction.model_validate(valid_transaction_data())
    assert transaction.amount == Decimal("10.00")


@pytest.mark.parametrize("field", ["amount", "gross_amount", "processing_fee", "provider_fee"])
def test_money_fields_cannot_be_negative(field: str) -> None:
    data = valid_transaction_data()
    data[field] = Decimal("-0.01")
    with pytest.raises(ValidationError):
        PayLensTransaction.model_validate(data)


def test_status_must_be_canonical() -> None:
    data = valid_transaction_data()
    data["status"] = "MAYBE"
    with pytest.raises(ValidationError):
        PayLensTransaction.model_validate(data)


def test_failed_transaction_requires_failure_details() -> None:
    data = valid_transaction_data()
    data["status"] = PaymentStatus.FAILED
    with pytest.raises(ValidationError, match="failure details"):
        PayLensTransaction.model_validate(data)


def test_timestamps_must_include_timezone() -> None:
    data = valid_transaction_data()
    data["transaction_created_at"] = datetime(2026, 6, 1)
    with pytest.raises(ValidationError, match="timezone"):
        PayLensTransaction.model_validate(data)


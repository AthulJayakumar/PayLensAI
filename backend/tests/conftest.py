from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.models import (
    CardNetwork,
    DisputeStatus,
    FailureCategory,
    FundingType,
    PaymentMethod,
    PaymentProvider,
    PaymentStatus,
    PayLensTransaction,
    RefundStatus,
    SourceType,
)


@pytest.fixture
def transaction_factory():
    counter = 0

    def make_transaction(**overrides) -> PayLensTransaction:
        nonlocal counter
        counter += 1
        created_at = overrides.pop(
            "transaction_created_at",
            datetime(2026, 6, 20, tzinfo=timezone.utc) + timedelta(seconds=counter),
        )
        amount = Decimal(str(overrides.pop("amount", "100")))
        status = overrides.pop("status", PaymentStatus.SUCCEEDED)
        processing_fee = Decimal(str(overrides.pop("processing_fee", "1")))
        provider_fee = Decimal(str(overrides.pop("provider_fee", "0.5")))
        other_cost = Decimal(str(overrides.pop("other_cost", "0.1")))
        refund_amount = Decimal(str(overrides.pop("refund_amount", "0")))
        dispute_amount = Decimal(str(overrides.pop("dispute_amount", "0")))
        if status != PaymentStatus.SUCCEEDED:
            processing_fee = provider_fee = other_cost = Decimal("0")
        refund_status = overrides.pop(
            "refund_status", RefundStatus.FULL if refund_amount else RefundStatus.NONE
        )
        dispute_status = overrides.pop(
            "dispute_status", DisputeStatus.OPEN if dispute_amount else DisputeStatus.NONE
        )
        failure = status == PaymentStatus.FAILED
        gross = amount if status == PaymentStatus.SUCCEEDED else Decimal("0")
        data = {
            "id": f"ptx_fixture_{counter}",
            "merchant_id": "merchant_fixture",
            "provider": PaymentProvider.STRIPE,
            "provider_transaction_id": f"provider_fixture_{counter}",
            "provider_reference": None,
            "transaction_created_at": created_at,
            "authorised_at": created_at if status == PaymentStatus.SUCCEEDED else None,
            "settled_at": None,
            "amount": amount,
            "currency": "GBP",
            "status": status,
            "provider_status": "succeeded" if not failure else "failed",
            "payment_method": PaymentMethod.CARD,
            "card_network": CardNetwork.VISA,
            "funding_type": FundingType.DEBIT,
            "issuer_country": "GB",
            "failure_code": "issuer_declined" if failure else None,
            "failure_category": FailureCategory.ISSUER_DECLINE if failure else None,
            "failure_message": "Declined" if failure else None,
            "provider_failure_code": "provider_declined" if failure else None,
            "provider_failure_message": "Declined" if failure else None,
            "gross_amount": gross,
            "processing_fee": processing_fee,
            "provider_fee": provider_fee,
            "other_cost": other_cost,
            "net_amount": max(
                Decimal("0"),
                gross - processing_fee - provider_fee - other_cost - refund_amount - dispute_amount,
            ),
            "refund_status": refund_status,
            "refund_amount": refund_amount,
            "dispute_status": dispute_status,
            "dispute_amount": dispute_amount,
            "dispute_reason": "FRAUDULENT" if dispute_amount else None,
            "settlement_date": None,
            "settlement_currency": None,
            "payout_reference": None,
            "source_type": SourceType.SYNTHETIC,
            "source_timestamp": created_at,
            "raw_data_reference": None,
            "data_availability": {},
            "created_at_internal": created_at,
            "updated_at_internal": created_at,
        }
        data.update(overrides)
        return PayLensTransaction.model_validate(data)

    return make_transaction


"""Provider-neutral canonical transaction model."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


Money = Annotated[Decimal, Field(ge=0, max_digits=20, decimal_places=6)]


class PaymentProvider(StrEnum):
    STRIPE = "STRIPE"
    PAYPAL = "PAYPAL"
    ADYEN = "ADYEN"


class PaymentStatus(StrEnum):
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    PENDING = "PENDING"
    CANCELLED = "CANCELLED"


class PaymentMethod(StrEnum):
    CARD = "CARD"
    PAYPAL = "PAYPAL"
    APPLE_PAY = "APPLE_PAY"
    GOOGLE_PAY = "GOOGLE_PAY"
    BANK_TRANSFER = "BANK_TRANSFER"


class CardNetwork(StrEnum):
    VISA = "VISA"
    MASTERCARD = "MASTERCARD"
    AMEX = "AMEX"
    DISCOVER = "DISCOVER"


class FundingType(StrEnum):
    CREDIT = "CREDIT"
    DEBIT = "DEBIT"
    PREPAID = "PREPAID"
    UNKNOWN = "UNKNOWN"


class FailureCategory(StrEnum):
    ISSUER_DECLINE = "ISSUER_DECLINE"
    AUTHENTICATION = "AUTHENTICATION"
    INSUFFICIENT_FUNDS = "INSUFFICIENT_FUNDS"
    TECHNICAL = "TECHNICAL"
    FRAUD = "FRAUD"
    INVALID_PAYMENT_DETAILS = "INVALID_PAYMENT_DETAILS"
    UNKNOWN = "UNKNOWN"


class RefundStatus(StrEnum):
    NONE = "NONE"
    PARTIAL = "PARTIAL"
    FULL = "FULL"
    PENDING = "PENDING"


class DisputeStatus(StrEnum):
    NONE = "NONE"
    OPEN = "OPEN"
    WON = "WON"
    LOST = "LOST"


class SourceType(StrEnum):
    API = "API"
    WEBHOOK = "WEBHOOK"
    REPORT = "REPORT"
    CSV = "CSV"
    SYNTHETIC = "SYNTHETIC"


class DataAvailability(StrEnum):
    AVAILABLE = "AVAILABLE"
    NOT_AVAILABLE = "NOT_AVAILABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    NOT_PROVIDED = "NOT_PROVIDED"
    PENDING = "PENDING"


class PayLensTransaction(BaseModel):
    """A validated canonical payment attempt.

    Refund and dispute lifecycle fields do not replace the original payment status.
    Provider-native values are retained alongside normalised values.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: str = Field(min_length=1, max_length=100)
    merchant_id: str = Field(min_length=1, max_length=100)

    provider: PaymentProvider
    provider_transaction_id: str = Field(min_length=1, max_length=255)
    provider_reference: str | None = Field(default=None, max_length=255)

    transaction_created_at: datetime
    authorised_at: datetime | None = None
    settled_at: datetime | None = None

    amount: Money
    currency: str = Field(pattern=r"^[A-Z]{3}$")

    status: PaymentStatus
    provider_status: str = Field(min_length=1, max_length=100)

    payment_method: PaymentMethod
    card_network: CardNetwork | None = None
    funding_type: FundingType | None = None
    issuer_country: str | None = Field(default=None, pattern=r"^[A-Z]{2}$")

    failure_code: str | None = Field(default=None, max_length=100)
    failure_category: FailureCategory | None = None
    failure_message: str | None = Field(default=None, max_length=500)
    provider_failure_code: str | None = Field(default=None, max_length=100)
    provider_failure_message: str | None = Field(default=None, max_length=500)

    gross_amount: Money
    processing_fee: Money
    provider_fee: Money
    other_cost: Money
    net_amount: Money

    refund_status: RefundStatus = RefundStatus.NONE
    refund_amount: Money = Decimal("0")

    dispute_status: DisputeStatus = DisputeStatus.NONE
    dispute_amount: Money = Decimal("0")
    dispute_reason: str | None = Field(default=None, max_length=255)

    settlement_date: datetime | None = None
    settlement_currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    payout_reference: str | None = Field(default=None, max_length=255)

    source_type: SourceType
    source_timestamp: datetime
    raw_data_reference: str | None = Field(default=None, max_length=500)
    data_availability: dict[str, DataAvailability] = Field(default_factory=dict)

    created_at_internal: datetime
    updated_at_internal: datetime

    @field_validator(
        "transaction_created_at",
        "authorised_at",
        "settled_at",
        "settlement_date",
        "source_timestamp",
        "created_at_internal",
        "updated_at_internal",
    )
    @classmethod
    def timestamps_must_be_timezone_aware(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("timestamps must include a timezone")
        return value

    @model_validator(mode="after")
    def validate_lifecycle_consistency(self) -> PayLensTransaction:
        if self.status == PaymentStatus.FAILED:
            if self.failure_category is None or self.failure_code is None:
                raise ValueError("failed transactions require failure details")
        elif any(
            value is not None
            for value in (self.failure_code, self.failure_category, self.failure_message)
        ):
            raise ValueError("non-failed transactions cannot have canonical failure details")

        if self.refund_status == RefundStatus.NONE and self.refund_amount != 0:
            raise ValueError("refund amount must be zero when refund status is NONE")
        if self.refund_status != RefundStatus.NONE and self.refund_amount <= 0:
            raise ValueError("refunded transactions require a positive refund amount")
        if self.refund_amount > self.amount:
            raise ValueError("refund amount cannot exceed transaction amount")

        if self.dispute_status == DisputeStatus.NONE and self.dispute_amount != 0:
            raise ValueError("dispute amount must be zero when dispute status is NONE")
        if self.dispute_status != DisputeStatus.NONE and self.dispute_amount <= 0:
            raise ValueError("disputed transactions require a positive dispute amount")
        if self.dispute_amount > self.amount:
            raise ValueError("dispute amount cannot exceed transaction amount")

        if self.updated_at_internal < self.created_at_internal:
            raise ValueError("updated_at_internal cannot precede created_at_internal")
        if self.settled_at is not None and self.authorised_at is None:
            raise ValueError("settled transactions require an authorisation timestamp")
        return self


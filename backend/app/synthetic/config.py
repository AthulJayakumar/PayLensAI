"""Configuration models for deterministic synthetic generation."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models import CardNetwork, PaymentMethod, PaymentProvider


class AnomalyType(StrEnum):
    """Synthetic problem families that the generator can deliberately inject."""

    FAILURE_SPIKE = "FAILURE_SPIKE"
    NETWORK_SPECIFIC_FAILURE = "NETWORK_SPECIFIC_FAILURE"
    COUNTRY_SPECIFIC_FAILURE = "COUNTRY_SPECIFIC_FAILURE"
    HIGH_PROVIDER_FEES = "HIGH_PROVIDER_FEES"
    REFUND_SPIKE = "REFUND_SPIKE"
    DISPUTE_SPIKE = "DISPUTE_SPIKE"


class AnomalyRule(BaseModel):
    """Selectors, time window, and strength for one injected anomaly."""

    model_config = ConfigDict(extra="forbid")

    type: AnomalyType
    probability: float | None = Field(default=None, ge=0, le=1)
    multiplier: float | None = Field(default=None, gt=0)
    provider: PaymentProvider | None = None
    payment_method: PaymentMethod | None = None
    card_network: CardNetwork | None = None
    issuer_country: str | None = Field(default=None, pattern=r"^[A-Z]{2}$")
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    start_at: datetime | None = None
    end_at: datetime | None = None

    @model_validator(mode="after")
    def validate_parameters(self) -> AnomalyRule:
        if self.type == AnomalyType.HIGH_PROVIDER_FEES:
            if self.multiplier is None or self.probability is not None:
                raise ValueError("HIGH_PROVIDER_FEES requires only multiplier")
        elif self.probability is None or self.multiplier is not None:
            raise ValueError(f"{self.type} requires only probability")
        if self.type == AnomalyType.NETWORK_SPECIFIC_FAILURE and self.card_network is None:
            raise ValueError("NETWORK_SPECIFIC_FAILURE requires card_network")
        if self.type == AnomalyType.COUNTRY_SPECIFIC_FAILURE and self.issuer_country is None:
            raise ValueError("COUNTRY_SPECIFIC_FAILURE requires issuer_country")
        if self.start_at and (self.start_at.tzinfo is None or self.start_at.utcoffset() is None):
            raise ValueError("start_at must include a timezone")
        if self.end_at and (self.end_at.tzinfo is None or self.end_at.utcoffset() is None):
            raise ValueError("end_at must include a timezone")
        if self.start_at and self.end_at and self.end_at <= self.start_at:
            raise ValueError("end_at must be after start_at")
        return self

    def matches(
        self,
        *,
        provider: PaymentProvider,
        payment_method: PaymentMethod,
        card_network: CardNetwork | None,
        issuer_country: str | None,
        currency: str,
        created_at: datetime,
    ) -> bool:
        selectors = (
            (self.provider, provider),
            (self.payment_method, payment_method),
            (self.card_network, card_network),
            (self.issuer_country, issuer_country),
            (self.currency, currency),
        )
        if any(expected is not None and expected != actual for expected, actual in selectors):
            return False
        if self.start_at is not None and created_at < self.start_at:
            return False
        return self.end_at is None or created_at < self.end_at


class GenerationConfig(BaseModel):
    """Validated recipe that makes a synthetic dataset reproducible."""

    model_config = ConfigDict(extra="forbid")

    count: int = Field(default=100_000, gt=0, le=10_000_000)
    seed: int = 20_260_822
    merchant_id: str = Field(default="merchant_demo_001", min_length=1, max_length=100)
    start_at: datetime = datetime(2026, 4, 1, tzinfo=timezone.utc)
    end_at: datetime = datetime(2026, 7, 1, tzinfo=timezone.utc)
    anomalies: list[AnomalyRule] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_date_range(self) -> GenerationConfig:
        if self.start_at.tzinfo is None or self.start_at.utcoffset() is None:
            raise ValueError("start_at must include a timezone")
        if self.end_at.tzinfo is None or self.end_at.utcoffset() is None:
            raise ValueError("end_at must include a timezone")
        if self.end_at <= self.start_at:
            raise ValueError("end_at must be after start_at")
        return self


def default_anomalies() -> list[AnomalyRule]:
    """Return a fresh default rule list demonstrating every supported anomaly."""

    return [
        AnomalyRule(
            type=AnomalyType.FAILURE_SPIKE,
            probability=0.14,
            provider=PaymentProvider.STRIPE,
            start_at=datetime(2026, 6, 16, tzinfo=timezone.utc),
        ),
        AnomalyRule(
            type=AnomalyType.NETWORK_SPECIFIC_FAILURE,
            probability=0.11,
            card_network=CardNetwork.MASTERCARD,
            issuer_country="US",
            start_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        ),
        AnomalyRule(
            type=AnomalyType.COUNTRY_SPECIFIC_FAILURE,
            probability=0.09,
            issuer_country="DE",
            start_at=datetime(2026, 6, 16, tzinfo=timezone.utc),
        ),
        AnomalyRule(
            type=AnomalyType.HIGH_PROVIDER_FEES,
            multiplier=1.8,
            provider=PaymentProvider.PAYPAL,
        ),
        AnomalyRule(
            type=AnomalyType.REFUND_SPIKE,
            probability=0.12,
            card_network=CardNetwork.VISA,
            issuer_country="GB",
            start_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        ),
        AnomalyRule(
            type=AnomalyType.DISPUTE_SPIKE,
            probability=0.045,
            provider=PaymentProvider.ADYEN,
            issuer_country="US",
            start_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        ),
    ]

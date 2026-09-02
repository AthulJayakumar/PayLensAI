"""Structured outputs for KPI, segmentation, and comparison analytics."""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


MoneyByCurrency = dict[str, Decimal]
RateByCurrency = dict[str, Decimal | None]


class SegmentDimension(StrEnum):
    """Fields by which a merchant can split payment performance."""

    PROVIDER = "provider"
    PAYMENT_METHOD = "payment_method"
    CARD_NETWORK = "card_network"
    ISSUER_COUNTRY = "issuer_country"
    CURRENCY = "currency"
    FAILURE_CATEGORY = "failure_category"
    TIME_PERIOD = "time_period"


class TimeGranularity(StrEnum):
    """Calendar bucket sizes supported by time-period segmentation."""

    DAY = "day"
    WEEK = "week"
    MONTH = "month"


class KPIMetrics(BaseModel):
    """Canonical KPI result.

    Rates use fractional representation: ``0.08`` means 8%. Money is kept by
    currency so incompatible currencies are never silently combined.
    """

    model_config = ConfigDict(extra="forbid")

    transaction_count: int = Field(ge=0)
    successful_transaction_count: int = Field(ge=0)
    failed_transaction_count: int = Field(ge=0)
    attempted_payment_value: MoneyByCurrency
    successful_payment_value: MoneyByCurrency
    failed_attempted_payment_value: MoneyByCurrency
    success_rate: Decimal = Field(ge=0, le=1)
    failure_rate: Decimal = Field(ge=0, le=1)
    average_transaction_value: MoneyByCurrency
    refund_amount: MoneyByCurrency
    refund_rate: Decimal = Field(ge=0, le=1)
    dispute_amount: MoneyByCurrency
    dispute_rate: Decimal = Field(ge=0, le=1)
    processing_fees: MoneyByCurrency
    provider_fees: MoneyByCurrency
    other_costs: MoneyByCurrency
    total_payment_cost: MoneyByCurrency
    effective_payment_cost_percentage: RateByCurrency


class SegmentMetrics(BaseModel):
    """The identifying segment values and KPIs calculated for that group."""

    model_config = ConfigDict(extra="forbid")

    segment: dict[str, str]
    metrics: KPIMetrics


class BaselineComparison(BaseModel):
    """Failure-rate comparison between historical and current populations."""

    model_config = ConfigDict(extra="forbid")

    segment: dict[str, str] = Field(default_factory=dict)
    baseline_failure_rate: Decimal = Field(ge=0, le=1)
    current_failure_rate: Decimal = Field(ge=0, le=1)
    absolute_difference: Decimal
    relative_percentage_change: Decimal | None
    affected_attempted_payment_value: MoneyByCurrency
    transaction_count: int = Field(ge=0)
    failed_transaction_count: int = Field(ge=0)
    baseline_transaction_count: int = Field(ge=0)
    baseline_failed_transaction_count: int = Field(ge=0)

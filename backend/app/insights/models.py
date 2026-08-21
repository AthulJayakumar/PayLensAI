"""Structured insight contracts."""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from app.analytics.models import KPIMetrics, MoneyByCurrency


class InsightType(StrEnum):
    FAILURE_SPIKE = "FAILURE_SPIKE"
    HIGH_FAILURE_SEGMENT = "HIGH_FAILURE_SEGMENT"
    HIGH_PAYMENT_COST = "HIGH_PAYMENT_COST"
    PROVIDER_COST_DIFFERENCE = "PROVIDER_COST_DIFFERENCE"
    REFUND_SPIKE = "REFUND_SPIKE"
    DISPUTE_SPIKE = "DISPUTE_SPIKE"
    PAYMENT_METHOD_UNDERPERFORMANCE = "PAYMENT_METHOD_UNDERPERFORMANCE"


class Severity(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class DetectionContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    segment: dict[str, str]
    baseline: KPIMetrics
    current: KPIMetrics


class Insight(BaseModel):
    """Machine-readable detector result; all rates are fractional."""

    model_config = ConfigDict(extra="forbid")

    id: str
    type: InsightType
    severity: Severity
    segment: dict[str, str]
    metric: str
    baseline_value: Decimal | None = None
    current_value: Decimal
    absolute_difference: Decimal | None = None
    relative_change: Decimal | None = None
    affected_attempted_value: MoneyByCurrency = Field(default_factory=dict)
    affected_refund_amount: MoneyByCurrency = Field(default_factory=dict)
    affected_dispute_amount: MoneyByCurrency = Field(default_factory=dict)
    affected_payment_cost: MoneyByCurrency = Field(default_factory=dict)
    transaction_count: int = Field(ge=0)
    affected_transaction_count: int = Field(ge=0)
    confidence: Decimal = Field(ge=0, le=1)
    evidence: dict[str, str | int | Decimal] = Field(default_factory=dict)


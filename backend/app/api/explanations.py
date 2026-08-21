"""Deterministic merchant-readable explanations for structured insights."""

from __future__ import annotations

from abc import ABC, abstractmethod
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.analytics.models import MoneyByCurrency
from app.insights.models import Insight, InsightType


class Explanation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    what_happened: str
    why_it_matters: str
    what_to_investigate: str


class ExplanationProvider(ABC):
    @abstractmethod
    def explain(self, insight: Insight) -> Explanation:
        """Convert one calculated finding into merchant-safe language."""


def _percentage(value: Decimal | None) -> str:
    return "not available" if value is None else f"{value * 100:.2f}%"


def _segment_label(segment: dict[str, str]) -> str:
    ordered = ("issuer_country", "card_network", "payment_method", "provider", "currency")
    values = [segment[key].replace("_", " ").title() for key in ordered if key in segment]
    return " ".join(values) or "Overall payment"


def _money_text(values: MoneyByCurrency) -> str:
    if not values:
        return "The affected monetary value is not available"
    parts = [f"{currency} {amount:,.2f}" for currency, amount in sorted(values.items())]
    return ", ".join(parts)


class TemplateExplanationProvider(ExplanationProvider):
    """Template-only implementation; no LLM or unsupported causal claims."""

    def explain(self, insight: Insight) -> Explanation:
        label = _segment_label(insight.segment)
        if insight.type in {
            InsightType.FAILURE_SPIKE,
            InsightType.HIGH_FAILURE_SEGMENT,
            InsightType.PAYMENT_METHOD_UNDERPERFORMANCE,
        }:
            happened = (
                f"{label} payment failures changed from {_percentage(insight.baseline_value)} "
                f"to {_percentage(insight.current_value)}."
            )
            matters = (
                f"{_money_text(insight.affected_attempted_value)} of attempted payment value "
                "was affected during the analysed period. Customers may retry successfully."
            )
            investigate = (
                "Review failure categories, authentication outcomes, issuer-decline patterns, "
                "and recent provider or checkout changes for this segment."
            )
        elif insight.type in {
            InsightType.HIGH_PAYMENT_COST,
            InsightType.PROVIDER_COST_DIFFERENCE,
        }:
            happened = (
                f"{label} effective payment cost is {_percentage(insight.current_value)}"
                + (
                    f" compared with {_percentage(insight.baseline_value)}."
                    if insight.baseline_value is not None
                    else "."
                )
            )
            matters = f"Recorded payment costs for this finding total {_money_text(insight.affected_payment_cost)}."
            investigate = (
                "Review provider pricing, card-network mix, cross-border charges, fixed fees, "
                "and whether the compared provider mix is commercially equivalent."
            )
        elif insight.type == InsightType.REFUND_SPIKE:
            happened = (
                f"{label} refund rate increased from {_percentage(insight.baseline_value)} "
                f"to {_percentage(insight.current_value)}."
            )
            matters = f"Recorded refunds in this segment total {_money_text(insight.affected_refund_amount)}."
            investigate = (
                "Review refund reasons, product or fulfilment incidents, duplicate charges, "
                "and recent operational changes affecting this segment."
            )
        else:
            happened = (
                f"{label} dispute rate increased from {_percentage(insight.baseline_value)} "
                f"to {_percentage(insight.current_value)}."
            )
            matters = f"Recorded disputed value in this segment totals {_money_text(insight.affected_dispute_amount)}."
            investigate = (
                "Review dispute reasons, fraud signals, fulfilment evidence, customer communications, "
                "and descriptor recognition for this segment."
            )
        return Explanation(
            what_happened=happened,
            why_it_matters=matters,
            what_to_investigate=investigate,
        )

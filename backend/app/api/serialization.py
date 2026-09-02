"""Lossless API serialization of existing analytics outputs."""

from __future__ import annotations

from decimal import Decimal

from app.analytics.models import KPIMetrics
from app.insights.models import Insight


def decimal_text(value: Decimal | None) -> str | None:
    """Serialize an exact decimal as text so JSON does not lose precision."""

    return None if value is None else format(value, "f")


def money_map(values: dict[str, Decimal]) -> dict[str, str]:
    """Serialize a currency-to-amount mapping in stable currency order."""

    return {currency: decimal_text(value) for currency, value in sorted(values.items())}


def metrics_payload(metrics: KPIMetrics) -> dict:
    """Project internal KPI names into the public, currency-safe API shape."""

    currencies = sorted(metrics.attempted_payment_value)
    return {
        "overall": {
            "transaction_count": metrics.transaction_count,
            "successful_transaction_count": metrics.successful_transaction_count,
            "failed_transaction_count": metrics.failed_transaction_count,
            "success_rate": decimal_text(metrics.success_rate),
            "failure_rate": decimal_text(metrics.failure_rate),
            "refund_rate": decimal_text(metrics.refund_rate),
            "dispute_rate": decimal_text(metrics.dispute_rate),
        },
        "currencies": {
            currency: {
                "attempted_value": decimal_text(metrics.attempted_payment_value.get(currency)),
                "successful_value": decimal_text(metrics.successful_payment_value.get(currency, Decimal("0"))),
                "failed_attempted_value": decimal_text(
                    metrics.failed_attempted_payment_value.get(currency, Decimal("0"))
                ),
                "average_transaction_value": decimal_text(
                    metrics.average_transaction_value.get(currency)
                ),
                "refund_amount": decimal_text(metrics.refund_amount.get(currency, Decimal("0"))),
                "dispute_amount": decimal_text(metrics.dispute_amount.get(currency, Decimal("0"))),
                "processing_fees": decimal_text(
                    metrics.processing_fees.get(currency, Decimal("0"))
                ),
                "provider_fees": decimal_text(metrics.provider_fees.get(currency, Decimal("0"))),
                "other_costs": decimal_text(metrics.other_costs.get(currency, Decimal("0"))),
                "total_cost": decimal_text(metrics.total_payment_cost.get(currency, Decimal("0"))),
                "effective_cost_rate": decimal_text(
                    metrics.effective_payment_cost_percentage.get(currency)
                ),
            }
            for currency in currencies
        },
    }


def insight_payload(insight: Insight) -> dict:
    """Project one structured insight into its stable public API shape."""

    return {
        "insight_id": insight.id,
        "type": insight.type.value,
        "severity": insight.severity.value,
        "segment": insight.segment,
        "metric": insight.metric,
        "baseline": decimal_text(insight.baseline_value),
        "current": decimal_text(insight.current_value),
        "absolute_difference": decimal_text(insight.absolute_difference),
        "relative_change": decimal_text(insight.relative_change),
        "affected_attempted_value": money_map(insight.affected_attempted_value),
        "affected_refund_amount": money_map(insight.affected_refund_amount),
        "affected_dispute_amount": money_map(insight.affected_dispute_amount),
        "affected_payment_cost": money_map(insight.affected_payment_cost),
        "transaction_count": insight.transaction_count,
        "affected_transaction_count": insight.affected_transaction_count,
        "confidence": decimal_text(insight.confidence),
        "supporting_metrics": {
            key: decimal_text(value) if isinstance(value, Decimal) else value
            for key, value in insight.evidence.items()
        },
    }

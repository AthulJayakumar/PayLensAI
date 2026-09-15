"""Monthly cash-flow projections built from canonical payment transactions.

The projection deliberately keeps currencies separate. Adding GBP to USD would
produce a visually impressive but financially meaningless total.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from decimal import Decimal, ROUND_HALF_UP

from app.models import PaymentStatus, PayLensTransaction


MONEY_QUANTUM = Decimal("0.000001")
FLOW_FIELDS = (
    "attempted_value",
    "gross_inflow",
    "refunds",
    "disputed_value",
    "processing_fees",
    "provider_fees",
    "other_costs",
)


def _empty_bucket() -> dict[str, Decimal | int]:
    """Return independent counters for one month/currency grouping."""
    return {"transaction_count": 0, **{field: Decimal("0") for field in FLOW_FIELDS}}


def _money(value: Decimal) -> str:
    """Serialize money as a fixed, exact decimal string for the browser."""
    return format(value.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP), "f")


def _add_transaction(bucket: dict[str, Decimal | int], transaction: PayLensTransaction) -> None:
    """Accumulate the canonical values used by both monthly and provider views."""
    bucket["transaction_count"] = int(bucket["transaction_count"]) + 1
    bucket["attempted_value"] = Decimal(bucket["attempted_value"]) + transaction.amount
    if transaction.status == PaymentStatus.SUCCEEDED:
        bucket["gross_inflow"] = Decimal(bucket["gross_inflow"]) + transaction.gross_amount
    bucket["refunds"] = Decimal(bucket["refunds"]) + transaction.refund_amount
    bucket["disputed_value"] = Decimal(bucket["disputed_value"]) + transaction.dispute_amount
    bucket["processing_fees"] = Decimal(bucket["processing_fees"]) + transaction.processing_fee
    bucket["provider_fees"] = Decimal(bucket["provider_fees"]) + transaction.provider_fee
    bucket["other_costs"] = Decimal(bucket["other_costs"]) + transaction.other_cost


def _payload(key: tuple[str, ...], bucket: dict[str, Decimal | int], *, provider: bool) -> dict:
    """Calculate reconciled totals after all raw values have been accumulated."""
    processing_fees = Decimal(bucket["processing_fees"])
    provider_fees = Decimal(bucket["provider_fees"])
    other_costs = Decimal(bucket["other_costs"])
    refunds = Decimal(bucket["refunds"])
    disputed_value = Decimal(bucket["disputed_value"])
    gross_inflow = Decimal(bucket["gross_inflow"])
    service_charges = processing_fees + provider_fees + other_costs
    money_out = refunds + disputed_value
    total_reductions = service_charges + money_out

    identity = (
        {"period": key[0], "provider": key[1], "currency": key[2]}
        if provider
        else {"period": key[0], "currency": key[1]}
    )
    return {
        **identity,
        "transaction_count": int(bucket["transaction_count"]),
        **{field: _money(Decimal(bucket[field])) for field in FLOW_FIELDS},
        "service_charges": _money(service_charges),
        "money_out": _money(money_out),
        "total_reductions": _money(total_reductions),
        "net_inflow": _money(gross_inflow - total_reductions),
    }


def monthly_cash_flow(transactions: Iterable[PayLensTransaction]) -> dict:
    """Return monthly merchant cash flow and provider charge breakdowns in one pass.

    ``gross_inflow`` is successful gross payment value. ``money_out`` is the
    recorded refund plus disputed value. Provider service charges are kept
    separate, and ``net_inflow`` subtracts both categories from gross inflow.
    Failed attempted value is never presented as cash out or lost revenue.
    """
    monthly: defaultdict[tuple[str, str], dict[str, Decimal | int]] = defaultdict(_empty_bucket)
    providers: defaultdict[tuple[str, str, str], dict[str, Decimal | int]] = defaultdict(_empty_bucket)
    totals: defaultdict[str, dict[str, Decimal | int]] = defaultdict(_empty_bucket)

    for transaction in transactions:
        period = transaction.transaction_created_at.strftime("%Y-%m")
        provider = transaction.provider.value
        _add_transaction(monthly[(period, transaction.currency)], transaction)
        _add_transaction(providers[(period, provider, transaction.currency)], transaction)
        _add_transaction(totals[transaction.currency], transaction)

    return {
        "definitions": {
            "gross_inflow": "Successful gross payment value processed during the month.",
            "money_out": "Recorded refunds plus disputed value; failed attempts are excluded.",
            "service_charges": "Processing fees plus provider fees plus other payment costs.",
            "net_inflow": "Gross inflow minus money out and service charges.",
            "currency_policy": "Every amount is reported per currency; currencies are never combined.",
            "provider_fee_note": "Some providers expose one combined fee. Stripe combined balance fees are reported as processing fees when a separate provider fee is unavailable.",
        },
        "totals": [
            {key: value for key, value in _payload(("ALL", currency), totals[currency], provider=False).items() if key != "period"}
            for currency in sorted(totals)
        ],
        "periods": [_payload(key, monthly[key], provider=False) for key in sorted(monthly)],
        "provider_costs": [_payload(key, providers[key], provider=True) for key in sorted(providers)],
    }

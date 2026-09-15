"""Monthly cash-flow projections built from canonical payment transactions.

Native views keep currencies separate. The optional whole-business GBP view
uses provider settlement evidence and reports any records it cannot convert.
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


def _gbp_values(transaction: PayLensTransaction) -> tuple[Decimal, Decimal, Decimal] | None:
    """Return gross inflow, money out and service charges in GBP when evidenced.

    Native GBP values need no conversion. For another payment currency, exact
    provider settlement gross/fee fields are preferred, while refunds, disputes,
    and separately modelled costs require the provider's source-to-GBP rate.
    """
    service_charges = transaction.processing_fee + transaction.provider_fee + transaction.other_cost
    money_out = transaction.refund_amount + transaction.dispute_amount
    gross = transaction.gross_amount if transaction.status == PaymentStatus.SUCCEEDED else Decimal("0")
    if transaction.currency == "GBP":
        return gross, money_out, service_charges
    if transaction.settlement_currency != "GBP":
        return None

    rate = transaction.exchange_rate
    if gross and transaction.settlement_gross_amount is None:
        return None
    if transaction.processing_fee and transaction.settlement_fee is None and rate is None:
        return None
    if (money_out or transaction.provider_fee or transaction.other_cost) and rate is None:
        return None

    settlement_gross = (
        transaction.settlement_gross_amount
        if gross and transaction.settlement_gross_amount is not None
        else Decimal("0")
    )
    settlement_processing_fee = (
        transaction.settlement_fee
        if transaction.settlement_fee is not None
        else transaction.processing_fee * (rate or Decimal("0"))
    )
    converted_extra_costs = (transaction.provider_fee + transaction.other_cost) * (rate or Decimal("0"))
    converted_money_out = money_out * (rate or Decimal("0"))
    return settlement_gross, converted_money_out, settlement_processing_fee + converted_extra_costs


def _empty_gbp_bucket() -> dict:
    """Create mutable counters for the audited GBP view."""
    return {
        "gross_inflow": Decimal("0"), "money_out": Decimal("0"), "service_charges": Decimal("0"),
        "cash_activity_count": 0, "included_count": 0, "excluded_count": 0,
        "native_gbp_count": 0, "provider_conversion_count": 0, "excluded_currencies": set(),
    }


def _add_gbp_transaction(bucket: dict, transaction: PayLensTransaction) -> None:
    """Accumulate one transaction without adding another pass over the dataset."""
    has_cash_activity = any(
        value
        for value in (
            transaction.gross_amount if transaction.status == PaymentStatus.SUCCEEDED else Decimal("0"),
            transaction.refund_amount,
            transaction.dispute_amount,
            transaction.processing_fee,
            transaction.provider_fee,
            transaction.other_cost,
        )
    )
    if not has_cash_activity:
        return
    bucket["cash_activity_count"] += 1
    converted = _gbp_values(transaction)
    if converted is None:
        bucket["excluded_count"] += 1
        bucket["excluded_currencies"].add(transaction.currency)
        return
    bucket["included_count"] += 1
    count_key = "native_gbp_count" if transaction.currency == "GBP" else "provider_conversion_count"
    bucket[count_key] += 1
    converted_gross, converted_out, converted_charges = converted
    bucket["gross_inflow"] += converted_gross
    bucket["money_out"] += converted_out
    bucket["service_charges"] += converted_charges


def _gbp_payload(bucket: dict) -> dict:
    """Serialize the audited UK reporting-currency accumulator."""
    coverage_rate = (
        Decimal(bucket["included_count"]) / Decimal(bucket["cash_activity_count"])
        if bucket["cash_activity_count"]
        else Decimal("1")
    )
    total_reductions = bucket["money_out"] + bucket["service_charges"]
    return {
        "reporting_currency": "GBP",
        "gross_inflow": _money(bucket["gross_inflow"]),
        "money_out": _money(bucket["money_out"]),
        "service_charges": _money(bucket["service_charges"]),
        "total_reductions": _money(total_reductions),
        "net_inflow": _money(bucket["gross_inflow"] - total_reductions),
        "cash_activity_transaction_count": bucket["cash_activity_count"],
        "included_transaction_count": bucket["included_count"],
        "excluded_transaction_count": bucket["excluded_count"],
        "native_gbp_transaction_count": bucket["native_gbp_count"],
        "provider_converted_transaction_count": bucket["provider_conversion_count"],
        "conversion_coverage_rate": format(coverage_rate.quantize(Decimal("0.000001")), "f"),
        "excluded_currencies": sorted(bucket["excluded_currencies"]),
        "is_complete": bucket["excluded_count"] == 0,
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
    gbp = _empty_gbp_bucket()

    for transaction in transactions:
        period = transaction.transaction_created_at.strftime("%Y-%m")
        provider = transaction.provider.value
        _add_transaction(monthly[(period, transaction.currency)], transaction)
        _add_transaction(providers[(period, provider, transaction.currency)], transaction)
        _add_transaction(totals[transaction.currency], transaction)
        _add_gbp_transaction(gbp, transaction)

    return {
        "definitions": {
            "gross_inflow": "Successful gross payment value processed during the month.",
            "money_out": "Recorded refunds plus disputed value; failed attempts are excluded.",
            "service_charges": "Processing fees plus provider fees plus other payment costs.",
            "net_inflow": "Gross inflow minus money out and service charges.",
            "currency_policy": "Every amount is reported per currency; currencies are never combined.",
            "gbp_policy": "The whole-business GBP total uses native GBP values or provider-supplied settlement amounts and exchange rates. Unsupported conversions are excluded and counted.",
            "provider_fee_note": "Some providers expose one combined fee. Stripe combined balance fees are reported as processing fees when a separate provider fee is unavailable.",
        },
        "gbp_summary": _gbp_payload(gbp),
        "totals": [
            {key: value for key, value in _payload(("ALL", currency), totals[currency], provider=False).items() if key != "period"}
            for currency in sorted(totals)
        ],
        "periods": [_payload(key, monthly[key], provider=False) for key in sorted(monthly)],
        "provider_costs": [_payload(key, providers[key], provider=True) for key in sorted(providers)],
    }

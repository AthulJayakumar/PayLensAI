"""Exact deterministic KPI calculations over canonical transactions."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from decimal import Decimal, ROUND_HALF_UP

from app.analytics.models import KPIMetrics, MoneyByCurrency
from app.models import DisputeStatus, PaymentStatus, PayLensTransaction, RefundStatus


RATE_QUANTUM = Decimal("0.000001")
MONEY_QUANTUM = Decimal("0.000001")


def rate(numerator: int | Decimal, denominator: int | Decimal) -> Decimal:
    """Return a six-decimal fraction, or zero for a zero denominator."""

    if denominator == 0:
        return Decimal("0")
    return (Decimal(numerator) / Decimal(denominator)).quantize(
        RATE_QUANTUM, rounding=ROUND_HALF_UP
    )


def _add(target: defaultdict[str, Decimal], currency: str, value: Decimal) -> None:
    target[currency] += value


def _normalise_money(values: defaultdict[str, Decimal]) -> MoneyByCurrency:
    return {
        currency: value.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
        for currency, value in sorted(values.items())
    }


def calculate_kpis(transactions: Iterable[PayLensTransaction]) -> KPIMetrics:
    """Calculate merchant payment KPIs without mixing currencies.

    Denominators:
    - success/failure rate: all payment attempts;
    - average transaction value: attempts in the same currency;
    - refund/dispute rate: successful payment transactions;
    - effective cost percentage: successful processed value in the same currency.
    """

    # Counts drive rate denominators; currency maps keep monetary values impossible to mix.
    transaction_count = successful_count = failed_count = 0
    refund_count = dispute_count = 0
    currency_counts: defaultdict[str, int] = defaultdict(int)
    attempted: defaultdict[str, Decimal] = defaultdict(Decimal)
    successful: defaultdict[str, Decimal] = defaultdict(Decimal)
    failed: defaultdict[str, Decimal] = defaultdict(Decimal)
    refunds: defaultdict[str, Decimal] = defaultdict(Decimal)
    disputes: defaultdict[str, Decimal] = defaultdict(Decimal)
    processing_fees: defaultdict[str, Decimal] = defaultdict(Decimal)
    provider_fees: defaultdict[str, Decimal] = defaultdict(Decimal)
    other_costs: defaultdict[str, Decimal] = defaultdict(Decimal)

    # One pass accumulates all raw counts and amounts, including zero-valued optional costs.
    for transaction in transactions:
        transaction_count += 1
        currency_counts[transaction.currency] += 1
        _add(attempted, transaction.currency, transaction.amount)
        _add(processing_fees, transaction.currency, transaction.processing_fee)
        _add(provider_fees, transaction.currency, transaction.provider_fee)
        _add(other_costs, transaction.currency, transaction.other_cost)

        if transaction.status == PaymentStatus.SUCCEEDED:
            successful_count += 1
            _add(successful, transaction.currency, transaction.gross_amount)
        elif transaction.status == PaymentStatus.FAILED:
            failed_count += 1
            _add(failed, transaction.currency, transaction.amount)

        if transaction.refund_status != RefundStatus.NONE:
            refund_count += 1
        if transaction.dispute_status != DisputeStatus.NONE:
            dispute_count += 1
        _add(refunds, transaction.currency, transaction.refund_amount)
        _add(disputes, transaction.currency, transaction.dispute_amount)

    # Derived per-currency values are calculated only after the raw pass is complete.
    average = defaultdict(Decimal)
    total_costs = defaultdict(Decimal)
    effective_cost: dict[str, Decimal | None] = {}
    currencies = sorted(
        set(attempted) | set(successful) | set(processing_fees) | set(provider_fees) | set(other_costs)
    )
    for currency in currencies:
        average[currency] = attempted[currency] / currency_counts[currency]
        total_costs[currency] = (
            processing_fees.get(currency, Decimal("0"))
            + provider_fees.get(currency, Decimal("0"))
            + other_costs.get(currency, Decimal("0"))
        )
        successful_value = successful.get(currency, Decimal("0"))
        effective_cost[currency] = (
            rate(total_costs[currency], successful_value)
            if successful_value != 0
            else None
        )

    # Pydantic returns one stable, typed result used by APIs, segments, and detectors.
    return KPIMetrics(
        transaction_count=transaction_count,
        successful_transaction_count=successful_count,
        failed_transaction_count=failed_count,
        attempted_payment_value=_normalise_money(attempted),
        successful_payment_value=_normalise_money(successful),
        failed_attempted_payment_value=_normalise_money(failed),
        success_rate=rate(successful_count, transaction_count),
        failure_rate=rate(failed_count, transaction_count),
        average_transaction_value=_normalise_money(average),
        refund_amount=_normalise_money(refunds),
        refund_rate=rate(refund_count, successful_count),
        dispute_amount=_normalise_money(disputes),
        dispute_rate=rate(dispute_count, successful_count),
        processing_fees=_normalise_money(processing_fees),
        provider_fees=_normalise_money(provider_fees),
        other_costs=_normalise_money(other_costs),
        total_payment_cost=_normalise_money(total_costs),
        effective_payment_cost_percentage=effective_cost,
    )

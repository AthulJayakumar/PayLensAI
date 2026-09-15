"""Deterministic tests for merchant monthly money movement."""

from datetime import datetime, timezone
from decimal import Decimal

from app.analytics.cash_flow import monthly_cash_flow
from app.models import PaymentProvider, PaymentStatus


def test_monthly_cash_flow_reconciles_money_and_provider_charges(transaction_factory) -> None:
    transactions = [
        transaction_factory(
            transaction_created_at=datetime(2026, 1, 8, tzinfo=timezone.utc),
            amount="100", processing_fee="2", provider_fee="1", other_cost="0.5",
            refund_amount="10",
        ),
        transaction_factory(
            transaction_created_at=datetime(2026, 1, 9, tzinfo=timezone.utc),
            amount="50", status=PaymentStatus.FAILED,
        ),
        transaction_factory(
            transaction_created_at=datetime(2026, 2, 2, tzinfo=timezone.utc),
            provider=PaymentProvider.PAYPAL,
            amount="200", processing_fee="4", provider_fee="2", other_cost="1",
            dispute_amount="20",
        ),
    ]

    result = monthly_cash_flow(transactions)

    assert [row["period"] for row in result["periods"]] == ["2026-01", "2026-02"]
    january = result["periods"][0]
    assert january["transaction_count"] == 2
    assert Decimal(january["attempted_value"]) == Decimal("150")
    assert Decimal(january["gross_inflow"]) == Decimal("100")
    assert Decimal(january["money_out"]) == Decimal("10")
    assert Decimal(january["service_charges"]) == Decimal("3.5")
    assert Decimal(january["total_reductions"]) == Decimal("13.5")
    assert Decimal(january["net_inflow"]) == Decimal("86.5")

    february = result["periods"][1]
    assert Decimal(february["money_out"]) == Decimal("20")
    assert Decimal(february["service_charges"]) == Decimal("7")
    assert Decimal(february["net_inflow"]) == Decimal("173")
    assert {row["provider"] for row in result["provider_costs"]} == {"STRIPE", "PAYPAL"}
    total = result["totals"][0]
    assert Decimal(total["gross_inflow"]) == Decimal("300")
    assert Decimal(total["service_charges"]) == Decimal("10.5")
    assert Decimal(total["net_inflow"]) == Decimal("259.5")


def test_monthly_cash_flow_handles_an_empty_dataset() -> None:
    result = monthly_cash_flow([])
    assert result["periods"] == []
    assert result["provider_costs"] == []
    assert result["totals"] == []
    assert result["gbp_summary"]["gross_inflow"] == "0.000000"
    assert result["gbp_summary"]["conversion_coverage_rate"] == "1.000000"
    assert "never combined" in result["definitions"]["currency_policy"]


def test_whole_business_gbp_summary_uses_provider_fx_and_reports_exclusions(transaction_factory) -> None:
    transactions = [
        transaction_factory(
            amount="100", currency="GBP", processing_fee="2", provider_fee="0", other_cost="0",
            refund_amount="10",
        ),
        transaction_factory(
            amount="100", currency="USD", processing_fee="3", provider_fee="0", other_cost="0",
            refund_amount="10", settlement_currency="GBP", settlement_gross_amount="80",
            settlement_fee="2", settlement_net_amount="78", exchange_rate="0.8",
        ),
        transaction_factory(
            amount="50", currency="EUR", processing_fee="1", provider_fee="0", other_cost="0",
        ),
    ]

    summary = monthly_cash_flow(transactions)["gbp_summary"]

    assert Decimal(summary["gross_inflow"]) == Decimal("180")
    assert Decimal(summary["money_out"]) == Decimal("18")
    assert Decimal(summary["service_charges"]) == Decimal("4")
    assert Decimal(summary["net_inflow"]) == Decimal("158")
    assert summary["cash_activity_transaction_count"] == 3
    assert summary["included_transaction_count"] == 2
    assert summary["excluded_transaction_count"] == 1
    assert summary["conversion_coverage_rate"] == "0.666667"
    assert summary["excluded_currencies"] == ["EUR"]
    assert summary["is_complete"] is False

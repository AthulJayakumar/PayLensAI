"""End-to-end local verification of the 100k Sprint 3 product path."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from time import perf_counter

from fastapi.testclient import TestClient

from app.analytics.csv_loader import load_transactions_csv
from app.analytics.kpis import calculate_kpis
from app.api.main import create_app
from app.api.repositories import InMemoryAnalysisRepository
from app.insights.engine import InsightEngine


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify the PayLens 100k API path.")
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("synthetic-data/paylens-transactions.csv"),
    )
    return parser.parse_args()


def has_segment(insights: list[dict], insight_type: str, **segment: str) -> bool:
    return any(
        item["type"] == insight_type
        and all(item["segment"].get(key) == value for key, value in segment.items())
        for item in insights
    )


def main() -> None:
    args = parse_args()
    repository = InMemoryAnalysisRepository()
    client = TestClient(create_app(repository=repository))
    client.headers.update({"X-PayLens-Dev-Key": "paylens-sprint3-verification-key"})

    upload_started = perf_counter()
    with args.input.open("rb") as source:
        response = client.post(
            "/analysis/upload",
            files={"file": (args.input.name, source, "text/csv")},
        )
    upload_request_seconds = perf_counter() - upload_started
    response.raise_for_status()
    summary = response.json()
    analysis_id = summary["analysis_id"]

    api_started = perf_counter()
    kpi_response = client.get(f"/analysis/{analysis_id}/kpis")
    insight_response = client.get(f"/analysis/{analysis_id}/insights")
    api_response_seconds = perf_counter() - api_started
    kpi_response.raise_for_status()
    insight_response.raise_for_status()
    api_kpis = kpi_response.json()
    api_insights = insight_response.json()["insights"]

    dashboard_started = perf_counter()
    dashboard_responses = [
        client.get(f"/analysis/{analysis_id}"),
        client.get(f"/analysis/{analysis_id}/kpis"),
        client.get(f"/analysis/{analysis_id}/insights"),
        *[
            client.get(
                f"/analysis/{analysis_id}/segments",
                params={"dimensions": dimension},
            )
            for dimension in ("provider", "payment_method", "card_network", "issuer_country")
        ],
    ]
    dashboard_data_load_seconds = perf_counter() - dashboard_started
    assert all(item.status_code == 200 for item in dashboard_responses)

    direct_transactions = load_transactions_csv(args.input)
    direct_kpis = calculate_kpis(direct_transactions)
    current_start = datetime.fromisoformat(summary["comparison_period"]["current_start"])
    current_end = datetime.fromisoformat(summary["comparison_period"]["current_end"])
    direct_insights = InsightEngine().analyse(
        direct_transactions,
        current_start=current_start,
        current_end=current_end,
    )

    kpi_match = (
        api_kpis["overall"]["transaction_count"] == direct_kpis.transaction_count
        and api_kpis["overall"]["success_rate"] == format(direct_kpis.success_rate, "f")
        and api_kpis["overall"]["failure_rate"] == format(direct_kpis.failure_rate, "f")
        and all(
            api_kpis["currencies"][currency]["attempted_value"]
            == format(value, "f")
            for currency, value in direct_kpis.attempted_payment_value.items()
        )
    )
    insight_ids_match = {item["insight_id"] for item in api_insights} == {
        item.id for item in direct_insights
    }
    expected_anomalies = {
        "stripe_failure": has_segment(api_insights, "FAILURE_SPIKE", provider="STRIPE"),
        "mastercard_us_failure": has_segment(
            api_insights,
            "FAILURE_SPIKE",
            card_network="MASTERCARD",
            issuer_country="US",
        ),
        "germany_failure": has_segment(api_insights, "FAILURE_SPIKE", issuer_country="DE"),
        "paypal_cost": has_segment(api_insights, "HIGH_PAYMENT_COST", provider="PAYPAL"),
        "visa_gb_refund": has_segment(
            api_insights, "REFUND_SPIKE", card_network="VISA", issuer_country="GB"
        ),
        "adyen_us_dispute": has_segment(
            api_insights, "DISPUTE_SPIKE", provider="ADYEN", issuer_country="US"
        ),
    }
    verification = {
        "analysis_id": analysis_id,
        "transaction_count": summary["transaction_count"],
        "file_size": summary["file_size"],
        "currency_count": len(api_kpis["currencies"]),
        "insight_count": len(api_insights),
        "kpi_match": kpi_match,
        "insight_ids_match": insight_ids_match,
        "expected_anomalies": expected_anomalies,
        "all_expected_anomalies_detected": all(expected_anomalies.values()),
        "timings": {
            **summary["performance"],
            "upload_http_request_seconds": upload_request_seconds,
            "kpi_and_insight_api_response_seconds": api_response_seconds,
            "dashboard_data_load_seconds_sequential": dashboard_data_load_seconds,
        },
    }
    if not (
        verification["transaction_count"] == 100_000
        and kpi_match
        and insight_ids_match
        and verification["all_expected_anomalies_detected"]
    ):
        raise SystemExit(json.dumps(verification, indent=2))
    print(json.dumps(verification, indent=2))


if __name__ == "__main__":
    main()

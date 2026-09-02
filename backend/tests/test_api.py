from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO

import pytest
from fastapi.testclient import TestClient

from app.api.main import create_app
from app.api.repositories import InMemoryAnalysisRepository
from app.synthetic.config import AnomalyRule, AnomalyType, GenerationConfig
from app.synthetic.csv_export import export_transactions_csv
from app.synthetic.generator import generate_transactions

TEST_DEV_KEY = "paylens-test-key-at-least-16-characters"


def api_client(**app_options) -> TestClient:
    client = TestClient(create_app(**app_options))
    client.headers.update({"X-PayLens-Dev-Key": TEST_DEV_KEY})
    return client


@pytest.fixture(scope="module")
def api_context(tmp_path_factory):
    output = tmp_path_factory.mktemp("api-data") / "canonical.csv"
    anomalies = [
        AnomalyRule(
            type=AnomalyType.FAILURE_SPIKE,
            probability=0.50,
            provider="STRIPE",
            start_at=datetime(2026, 6, 16, tzinfo=timezone.utc),
        ),
        AnomalyRule(type=AnomalyType.HIGH_PROVIDER_FEES, multiplier=2, provider="PAYPAL"),
    ]
    export_transactions_csv(
        generate_transactions(GenerationConfig(count=20_000, seed=303, anomalies=anomalies)),
        output,
    )
    repository = InMemoryAnalysisRepository()
    client = api_client(repository=repository)
    response = client.post(
        "/analysis/upload",
        files={"file": ("canonical.csv", output.read_bytes(), "text/csv")},
    )
    assert response.status_code == 201, response.text
    return client, repository, response.json()["analysis_id"]


def test_health_endpoint() -> None:
    response = api_client().get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "paylens-api", "version": "0.6.0"}


def test_valid_upload_creates_retrievable_analysis(api_context) -> None:
    client, repository, analysis_id = api_context
    response = client.get(f"/analysis/{analysis_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["analysis_id"] == analysis_id
    assert body["status"] == "COMPLETED"
    assert body["transaction_count"] == 20_000
    assert repository.get(analysis_id) is not None


def test_non_csv_upload_is_rejected() -> None:
    response = api_client().post(
        "/analysis/upload", files={"file": ("payments.json", b"{}", "application/json")}
    )
    assert response.status_code == 415
    assert response.json()["error"]["code"] == "UNSUPPORTED_FILE_TYPE"


def test_invalid_csv_returns_structured_error() -> None:
    response = api_client().post(
        "/analysis/upload",
        files={"file": ("payments.csv", b"id,merchant_id\n1,m1\n", "text/csv")},
    )
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "INVALID_TRANSACTION_DATA"
    assert body["error"]["details"]


def test_empty_file_is_rejected() -> None:
    response = api_client().post(
        "/analysis/upload", files={"file": ("payments.csv", b"", "text/csv")}
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "EMPTY_FILE"


def test_oversized_upload_is_rejected_without_analysis() -> None:
    response = api_client(max_upload_bytes=10).post(
        "/analysis/upload",
        files={"file": ("payments.csv", b"a" * 11, "text/csv")},
    )
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "FILE_TOO_LARGE"


def test_analysis_not_found_is_structured() -> None:
    response = api_client().get("/analysis/analysis_missing")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ANALYSIS_NOT_FOUND"


def test_kpi_response_preserves_currency_and_decimal_accuracy(api_context) -> None:
    client, repository, analysis_id = api_context
    response = client.get(f"/analysis/{analysis_id}/kpis")
    assert response.status_code == 200
    body = response.json()
    record = repository.get(analysis_id)
    assert set(body["currencies"]) == {"AUD", "CAD", "EUR", "GBP", "USD"}
    assert body["overall"]["success_rate"] == format(record.result.kpis.success_rate, "f")
    assert body["currencies"]["GBP"]["attempted_value"] == format(
        record.result.kpis.attempted_payment_value["GBP"], "f"
    )
    assert isinstance(body["currencies"]["GBP"]["attempted_value"], str)
    assert "total" not in body["currencies"]


def test_segment_combinations_and_validation(api_context) -> None:
    client, _, analysis_id = api_context
    response = client.get(
        f"/analysis/{analysis_id}/segments",
        params={"dimensions": "provider,card_network,issuer_country"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["dimensions"] == ["provider", "card_network", "issuer_country"]
    assert body["segments"]
    assert set(body["segments"][0]["segment"]) == {
        "provider",
        "card_network",
        "issuer_country",
    }

    invalid = client.get(
        f"/analysis/{analysis_id}/segments", params={"dimensions": "provider,amount"}
    )
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "INVALID_SEGMENT_DIMENSIONS"


def test_insight_retrieval_filtering_and_explanation(api_context) -> None:
    client, _, analysis_id = api_context
    response = client.get(f"/analysis/{analysis_id}/insights")
    assert response.status_code == 200
    body = response.json()
    assert body["count"] > 0
    severities = [item["severity"] for item in body["insights"]]
    order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    assert severities == sorted(severities, key=order.get)

    first = body["insights"][0]
    detail = client.get(f"/analysis/{analysis_id}/insights/{first['insight_id']}")
    assert detail.status_code == 200
    explanation = detail.json()["explanation"]
    assert explanation["what_happened"]
    assert explanation["why_it_matters"]
    assert "lost revenue" not in explanation["why_it_matters"].lower()
    assert explanation["what_to_investigate"]

    filtered = client.get(
        f"/analysis/{analysis_id}/insights", params={"severity": first["severity"]}
    )
    assert filtered.status_code == 200
    assert all(item["severity"] == first["severity"] for item in filtered.json()["insights"])

    by_type = client.get(
        f"/analysis/{analysis_id}/insights", params={"type": first["type"]}
    )
    assert all(item["type"] == first["type"] for item in by_type.json()["insights"])


def test_provider_insight_filter_and_insight_not_found(api_context) -> None:
    client, _, analysis_id = api_context
    response = client.get(
        f"/analysis/{analysis_id}/insights", params={"provider": "paypal"}
    )
    assert response.status_code == 200
    assert response.json()["count"] > 0
    assert all(
        item["segment"].get("provider") == "PAYPAL" for item in response.json()["insights"]
    )

    missing = client.get(f"/analysis/{analysis_id}/insights/ins_missing")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "INSIGHT_NOT_FOUND"


def test_api_values_match_stored_direct_engine_result(api_context) -> None:
    client, repository, analysis_id = api_context
    record = repository.get(analysis_id)
    kpi_body = client.get(f"/analysis/{analysis_id}/kpis").json()
    insight_body = client.get(f"/analysis/{analysis_id}/insights").json()

    assert kpi_body["overall"]["transaction_count"] == record.result.kpis.transaction_count
    assert kpi_body["overall"]["failure_rate"] == format(
        record.result.kpis.failure_rate, "f"
    )
    assert {item["insight_id"] for item in insight_body["insights"]} == {
        item.id for item in record.result.insights
    }


def test_missing_upload_field_uses_structured_validation_error() -> None:
    response = api_client().post("/analysis/upload")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "REQUEST_VALIDATION_ERROR"

from decimal import Decimal

from app.insights.models import Severity
from app.insights.severity import classify_severity


def test_small_samples_are_low_severity_even_with_large_rate() -> None:
    assert (
        classify_severity(
            relative_change=Decimal("10"),
            current_rate=Decimal("0.8"),
            affected_values={"GBP": Decimal("50000")},
            sample_size=25,
        )
        == Severity.LOW
    )


def test_severity_combines_change_value_and_sample_size() -> None:
    assert (
        classify_severity(
            relative_change=Decimal("2.5"),
            current_rate=Decimal("0.18"),
            affected_values={"GBP": Decimal("12000")},
            sample_size=1500,
        )
        == Severity.CRITICAL
    )


def test_severity_does_not_sum_currencies() -> None:
    severity = classify_severity(
        relative_change=Decimal("0.6"),
        current_rate=Decimal("0.09"),
        affected_values={"GBP": Decimal("600"), "USD": Decimal("600")},
        sample_size=300,
    )
    assert severity == Severity.MEDIUM


from datetime import datetime, timezone

from app.analytics.models import SegmentDimension, TimeGranularity
from app.analytics.segmentation import MISSING_SEGMENT_VALUE, segment_metrics
from app.models import CardNetwork, FailureCategory, PaymentMethod, PaymentProvider, PaymentStatus


def test_multi_dimension_segmentation(transaction_factory) -> None:
    transactions = [
        transaction_factory(
            provider=PaymentProvider.STRIPE,
            card_network=CardNetwork.MASTERCARD,
            issuer_country="US",
        ),
        transaction_factory(
            provider=PaymentProvider.STRIPE,
            card_network=CardNetwork.MASTERCARD,
            issuer_country="US",
        ),
        transaction_factory(
            provider=PaymentProvider.ADYEN,
            card_network=CardNetwork.VISA,
            issuer_country="GB",
        ),
    ]
    groups = segment_metrics(
        transactions,
        [
            SegmentDimension.PROVIDER,
            SegmentDimension.ISSUER_COUNTRY,
            SegmentDimension.CARD_NETWORK,
        ],
    )
    by_segment = {tuple(item.segment.values()): item.metrics.transaction_count for item in groups}
    assert by_segment[("STRIPE", "US", "MASTERCARD")] == 2
    assert by_segment[("ADYEN", "GB", "VISA")] == 1


def test_missing_optional_segment_is_retained(transaction_factory) -> None:
    transaction = transaction_factory(
        payment_method=PaymentMethod.PAYPAL,
        card_network=None,
        funding_type=None,
    )
    groups = segment_metrics([transaction], [SegmentDimension.CARD_NETWORK])
    assert groups[0].segment["card_network"] == MISSING_SEGMENT_VALUE
    assert groups[0].metrics.transaction_count == 1


def test_time_period_segmentation(transaction_factory) -> None:
    transactions = [
        transaction_factory(
            transaction_created_at=datetime(2026, 5, 31, tzinfo=timezone.utc)
        ),
        transaction_factory(
            transaction_created_at=datetime(2026, 6, 1, tzinfo=timezone.utc)
        ),
    ]
    groups = segment_metrics(
        transactions,
        [SegmentDimension.TIME_PERIOD],
        time_granularity=TimeGranularity.MONTH,
    )
    assert [item.segment["time_period"] for item in groups] == ["2026-05", "2026-06"]


def test_every_requested_single_dimension_is_supported(transaction_factory) -> None:
    transaction = transaction_factory(
        provider=PaymentProvider.ADYEN,
        payment_method=PaymentMethod.CARD,
        card_network=CardNetwork.MASTERCARD,
        issuer_country="US",
        currency="EUR",
        status=PaymentStatus.FAILED,
    )
    expected = {
        SegmentDimension.PROVIDER: "ADYEN",
        SegmentDimension.PAYMENT_METHOD: "CARD",
        SegmentDimension.CARD_NETWORK: "MASTERCARD",
        SegmentDimension.ISSUER_COUNTRY: "US",
        SegmentDimension.CURRENCY: "EUR",
        SegmentDimension.FAILURE_CATEGORY: FailureCategory.ISSUER_DECLINE.value,
        SegmentDimension.TIME_PERIOD: "2026-06",
    }
    for dimension, value in expected.items():
        result = segment_metrics([transaction], [dimension])
        assert result[0].segment[dimension.value] == value

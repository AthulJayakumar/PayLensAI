"""Deterministic, streaming synthetic PayLens transaction generator."""

from __future__ import annotations

import random
import uuid
from collections.abc import Iterator, Sequence
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP

from app.models import (
    CardNetwork,
    DataAvailability,
    DisputeStatus,
    FailureCategory,
    FundingType,
    PaymentMethod,
    PaymentProvider,
    PaymentStatus,
    PayLensTransaction,
    RefundStatus,
    SourceType,
)
from app.synthetic.config import AnomalyRule, AnomalyType, GenerationConfig


PENNY = Decimal("0.01")
PROVIDERS = tuple(PaymentProvider)
NETWORKS = tuple(CardNetwork)
COUNTRIES = ("GB", "US", "DE", "FR", "NL", "IE", "CA", "AU")
CURRENCIES = ("GBP", "USD", "EUR", "CAD", "AUD")
FUNDING_TYPES = (FundingType.DEBIT, FundingType.CREDIT, FundingType.PREPAID)
FAILURES: tuple[tuple[FailureCategory, str, str], ...] = (
    (FailureCategory.ISSUER_DECLINE, "issuer_declined", "The issuer declined the payment."),
    (FailureCategory.AUTHENTICATION, "authentication_failed", "Payment authentication failed."),
    (FailureCategory.INSUFFICIENT_FUNDS, "insufficient_funds", "Insufficient funds."),
    (FailureCategory.TECHNICAL, "processing_error", "A provider processing error occurred."),
    (FailureCategory.FRAUD, "suspected_fraud", "The payment was blocked by fraud controls."),
)

PROVIDER_STATUS = {
    PaymentProvider.STRIPE: {True: "succeeded", False: "requires_payment_method"},
    PaymentProvider.PAYPAL: {True: "COMPLETED", False: "DENIED"},
    PaymentProvider.ADYEN: {True: "Authorised", False: "Refused"},
}
PROVIDER_FEE_RATE = {
    PaymentProvider.STRIPE: Decimal("0.0055"),
    PaymentProvider.PAYPAL: Decimal("0.0080"),
    PaymentProvider.ADYEN: Decimal("0.0045"),
}
PROCESSING_FEE_RATE = {
    CardNetwork.VISA: Decimal("0.0110"),
    CardNetwork.MASTERCARD: Decimal("0.0120"),
    CardNetwork.AMEX: Decimal("0.0180"),
    CardNetwork.DISCOVER: Decimal("0.0150"),
}


def _money(value: Decimal) -> Decimal:
    return max(value, Decimal("0")).quantize(PENNY, rounding=ROUND_HALF_UP)


def _weighted_choice(rng: random.Random, values: Sequence, weights: Sequence[float]):
    return rng.choices(values, weights=weights, k=1)[0]


def _matching_rules(
    config: GenerationConfig,
    anomaly_types: set[AnomalyType],
    *,
    provider: PaymentProvider,
    payment_method: PaymentMethod,
    card_network: CardNetwork | None,
    issuer_country: str | None,
    currency: str,
    created_at: datetime,
) -> list[AnomalyRule]:
    return [
        rule
        for rule in config.anomalies
        if rule.type in anomaly_types
        and rule.matches(
            provider=provider,
            payment_method=payment_method,
            card_network=card_network,
            issuer_country=issuer_country,
            currency=currency,
            created_at=created_at,
        )
    ]


def _rate(base: float, rules: list[AnomalyRule]) -> float:
    """Use the strongest matching injected rate so rule order is irrelevant."""

    return max([base, *(rule.probability or 0 for rule in rules)])


def generate_transactions(config: GenerationConfig) -> Iterator[PayLensTransaction]:
    """Yield exactly ``config.count`` validated transactions for a fixed seed."""

    rng = random.Random(config.seed)
    span_seconds = int((config.end_at - config.start_at).total_seconds())

    for index in range(config.count):
        provider = _weighted_choice(rng, PROVIDERS, (0.47, 0.28, 0.25))
        payment_method = _weighted_choice(
            rng,
            tuple(PaymentMethod),
            (0.65, 0.12, 0.10, 0.08, 0.05),
        )
        is_card_based = payment_method in {
            PaymentMethod.CARD,
            PaymentMethod.APPLE_PAY,
            PaymentMethod.GOOGLE_PAY,
        }
        card_network = (
            _weighted_choice(rng, NETWORKS, (0.48, 0.38, 0.10, 0.04))
            if is_card_based
            else None
        )
        funding_type = _weighted_choice(rng, FUNDING_TYPES, (0.56, 0.40, 0.04)) if is_card_based else None
        issuer_country = _weighted_choice(
            rng, COUNTRIES, (0.30, 0.25, 0.11, 0.09, 0.07, 0.05, 0.07, 0.06)
        )
        currency = _weighted_choice(rng, CURRENCIES, (0.32, 0.30, 0.25, 0.07, 0.06))
        created_at = config.start_at + timedelta(seconds=rng.randrange(span_seconds))

        # A log-normal distribution gives many ordinary purchases and a realistic tail.
        amount = _money(Decimal(str(min(rng.lognormvariate(3.5, 0.9), 5000))))
        amount = max(amount, Decimal("0.50"))

        base_failure_rate = 0.025
        if provider == PaymentProvider.PAYPAL:
            base_failure_rate += 0.008
        if card_network == CardNetwork.MASTERCARD and issuer_country == "US":
            base_failure_rate = 0.038
        elif card_network == CardNetwork.AMEX:
            base_failure_rate += 0.007

        failure_rules = _matching_rules(
            config,
            {
                AnomalyType.FAILURE_SPIKE,
                AnomalyType.NETWORK_SPECIFIC_FAILURE,
                AnomalyType.COUNTRY_SPECIFIC_FAILURE,
            },
            provider=provider,
            payment_method=payment_method,
            card_network=card_network,
            issuer_country=issuer_country,
            currency=currency,
            created_at=created_at,
        )
        succeeded = rng.random() >= _rate(base_failure_rate, failure_rules)
        status = PaymentStatus.SUCCEEDED if succeeded else PaymentStatus.FAILED
        provider_status = PROVIDER_STATUS[provider][succeeded]

        failure_category = failure_code = failure_message = None
        provider_failure_code = provider_failure_message = None
        if not succeeded:
            failure_category, failure_code, failure_message = _weighted_choice(
                rng, FAILURES, (0.47, 0.18, 0.19, 0.10, 0.06)
            )
            provider_failure_code = f"{provider.value.lower()}_{failure_code}"
            provider_failure_message = failure_message

        refund_rules = _matching_rules(
            config,
            {AnomalyType.REFUND_SPIKE},
            provider=provider,
            payment_method=payment_method,
            card_network=card_network,
            issuer_country=issuer_country,
            currency=currency,
            created_at=created_at,
        )
        dispute_rules = _matching_rules(
            config,
            {AnomalyType.DISPUTE_SPIKE},
            provider=provider,
            payment_method=payment_method,
            card_network=card_network,
            issuer_country=issuer_country,
            currency=currency,
            created_at=created_at,
        )
        has_refund = succeeded and rng.random() < _rate(0.018, refund_rules)
        has_dispute = succeeded and rng.random() < _rate(0.0035, dispute_rules)

        refund_status = RefundStatus.NONE
        refund_amount = Decimal("0")
        if has_refund:
            full_refund = rng.random() < 0.72
            refund_status = RefundStatus.FULL if full_refund else RefundStatus.PARTIAL
            refund_amount = amount if full_refund else _money(amount * Decimal(str(rng.uniform(0.1, 0.8))))

        dispute_status = DisputeStatus.NONE
        dispute_amount = Decimal("0")
        dispute_reason = None
        if has_dispute:
            dispute_status = _weighted_choice(
                rng, (DisputeStatus.OPEN, DisputeStatus.WON, DisputeStatus.LOST), (0.55, 0.22, 0.23)
            )
            dispute_amount = amount
            dispute_reason = _weighted_choice(
                rng,
                ("FRAUDULENT", "PRODUCT_NOT_RECEIVED", "DUPLICATE", "UNRECOGNISED"),
                (0.45, 0.25, 0.10, 0.20),
            )

        authorised_at = created_at + timedelta(seconds=rng.randint(1, 45)) if succeeded else None
        settled_at = authorised_at + timedelta(days=rng.randint(1, 3)) if authorised_at else None
        gross_amount = amount if succeeded else Decimal("0")
        processing_fee = (
            _money(amount * PROCESSING_FEE_RATE.get(card_network, Decimal("0.0090")))
            if succeeded
            else Decimal("0")
        )
        provider_fee = _money(amount * PROVIDER_FEE_RATE[provider]) if succeeded else Decimal("0")
        fee_rules = _matching_rules(
            config,
            {AnomalyType.HIGH_PROVIDER_FEES},
            provider=provider,
            payment_method=payment_method,
            card_network=card_network,
            issuer_country=issuer_country,
            currency=currency,
            created_at=created_at,
        )
        for rule in fee_rules:
            provider_fee = _money(provider_fee * Decimal(str(rule.multiplier)))
        other_cost = _money(amount * Decimal("0.0005")) if succeeded else Decimal("0")
        net_amount = _money(
            gross_amount - processing_fee - provider_fee - other_cost - refund_amount - dispute_amount
        )

        stable_id = uuid.uuid5(uuid.NAMESPACE_URL, f"paylens:{config.seed}:{index}").hex
        internal_timestamp = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(microseconds=index)
        yield PayLensTransaction(
            id=f"ptx_{stable_id}",
            merchant_id=config.merchant_id,
            provider=provider,
            provider_transaction_id=f"{provider.value.lower()}_{config.seed}_{index:09d}",
            provider_reference=f"ref_{stable_id[:20]}",
            transaction_created_at=created_at,
            authorised_at=authorised_at,
            settled_at=settled_at,
            amount=amount,
            currency=currency,
            status=status,
            provider_status=provider_status,
            payment_method=payment_method,
            card_network=card_network,
            funding_type=funding_type,
            issuer_country=issuer_country,
            failure_code=failure_code,
            failure_category=failure_category,
            failure_message=failure_message,
            provider_failure_code=provider_failure_code,
            provider_failure_message=provider_failure_message,
            gross_amount=gross_amount,
            processing_fee=processing_fee,
            provider_fee=provider_fee,
            other_cost=other_cost,
            net_amount=net_amount,
            refund_status=refund_status,
            refund_amount=refund_amount,
            dispute_status=dispute_status,
            dispute_amount=dispute_amount,
            dispute_reason=dispute_reason,
            settlement_date=settled_at,
            settlement_currency=currency if settled_at else None,
            payout_reference=f"payout_{created_at:%Y%m%d}" if settled_at else None,
            source_type=SourceType.SYNTHETIC,
            source_timestamp=created_at,
            raw_data_reference=f"synthetic://{config.seed}/{index}",
            data_availability={
                "card_network": (
                    DataAvailability.AVAILABLE if card_network else DataAvailability.NOT_APPLICABLE
                ),
                "settlement_date": (
                    DataAvailability.AVAILABLE if settled_at else DataAvailability.PENDING
                ),
            },
            created_at_internal=internal_timestamp,
            updated_at_internal=internal_timestamp,
        )


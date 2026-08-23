"""Loss-aware Stripe PaymentIntent to canonical PayLens mapping."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from decimal import Decimal

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


ZERO_DECIMAL_CURRENCIES = {"BIF", "CLP", "DJF", "GNF", "JPY", "KMF", "KRW", "MGA", "PYG", "RWF", "UGX", "VND", "VUV", "XAF", "XOF", "XPF"}


def _money(value: int | None, currency: str) -> Decimal:
    """Convert Stripe minor units while respecting zero-decimal currencies."""
    amount = Decimal(value or 0)
    return amount if currency in ZERO_DECIMAL_CURRENCIES else amount / Decimal("100")


def _timestamp(value: int | None) -> datetime | None:
    return None if value is None else datetime.fromtimestamp(value, tz=timezone.utc)


FAILURE_MAP = {
    "card_declined": FailureCategory.ISSUER_DECLINE,
    "insufficient_funds": FailureCategory.INSUFFICIENT_FUNDS,
    "authentication_required": FailureCategory.AUTHENTICATION,
    "incorrect_cvc": FailureCategory.INVALID_PAYMENT_DETAILS,
    "expired_card": FailureCategory.INVALID_PAYMENT_DETAILS,
    "fraudulent": FailureCategory.FRAUD,
    "processing_error": FailureCategory.TECHNICAL,
}


class StripeNormalizer:
    """Translate one Stripe PaymentIntent without discarding provider evidence."""
    schema_version = "stripe-payment-intent-v1"

    def normalize(
        self,
        payment_intent: dict,
        *,
        merchant_id: str,
        raw_reference: str,
        source: SourceType,
    ) -> PayLensTransaction:
        """Map status, method, costs, refund/dispute data, and availability flags."""
        provider_id = payment_intent["id"]
        currency = str(payment_intent["currency"]).upper()
        provider_status = str(payment_intent.get("status", "unknown"))
        error = payment_intent.get("last_payment_error") or {}
        # Stripe exposes a richer lifecycle; PayLens maps it into stable states
        # while retaining the original value in ``provider_status``.
        if provider_status == "succeeded":
            status = PaymentStatus.SUCCEEDED
        elif provider_status == "canceled":
            status = PaymentStatus.CANCELLED
        elif error:
            status = PaymentStatus.FAILED
        else:
            status = PaymentStatus.PENDING

        # Expanded API responses contain an object, whereas lean webhook payloads
        # can contain only the charge ID. Both shapes are supported.
        charge = payment_intent.get("latest_charge") or {}
        if isinstance(charge, str):
            charge = {"id": charge}
        details = charge.get("payment_method_details") or {}
        method_type = details.get("type") or payment_intent.get("payment_method_types", ["card"])[0]
        card = details.get("card") or {}
        wallet = card.get("wallet") or {}
        wallet_type = wallet.get("type")
        if wallet_type == "apple_pay":
            payment_method = PaymentMethod.APPLE_PAY
        elif wallet_type == "google_pay":
            payment_method = PaymentMethod.GOOGLE_PAY
        elif method_type == "card":
            payment_method = PaymentMethod.CARD
        elif method_type in {"customer_balance", "us_bank_account", "sepa_debit", "bacs_debit"}:
            payment_method = PaymentMethod.BANK_TRANSFER
        else:
            payment_method = PaymentMethod.CARD

        brand_map = {"visa": CardNetwork.VISA, "mastercard": CardNetwork.MASTERCARD, "amex": CardNetwork.AMEX, "discover": CardNetwork.DISCOVER}
        funding_map = {"credit": FundingType.CREDIT, "debit": FundingType.DEBIT, "prepaid": FundingType.PREPAID, "unknown": FundingType.UNKNOWN}
        balance = charge.get("balance_transaction") or {}
        if isinstance(balance, str):
            balance = {}
        amount = _money(payment_intent.get("amount"), currency)
        gross = _money(payment_intent.get("amount_received"), currency) if status == PaymentStatus.SUCCEEDED else Decimal("0")
        processing_fee = _money(balance.get("fee"), currency)
        refund_amount = _money(charge.get("amount_refunded"), currency)
        dispute = charge.get("dispute") or {}
        disputed = bool(charge.get("disputed") or dispute)
        dispute_amount = _money(dispute.get("amount", charge.get("amount") if disputed else 0), currency)
        failure_code = error.get("decline_code") or error.get("code")
        failure_category = FAILURE_MAP.get(failure_code or "", FailureCategory.UNKNOWN) if status == PaymentStatus.FAILED else None
        created_at = _timestamp(payment_intent.get("created")) or datetime.now(timezone.utc)
        now = datetime.now(timezone.utc)
        internal_id = "ptx_" + hashlib.sha256(f"{merchant_id}:STRIPE:{provider_id}".encode()).hexdigest()[:32]
        net = max(Decimal("0"), gross - processing_fee - refund_amount - dispute_amount)

        return PayLensTransaction(
            id=internal_id,
            merchant_id=merchant_id,
            provider=PaymentProvider.STRIPE,
            provider_transaction_id=provider_id,
            provider_reference=charge.get("id"),
            transaction_created_at=created_at,
            authorised_at=created_at if status == PaymentStatus.SUCCEEDED else None,
            settled_at=None,
            amount=amount,
            currency=currency,
            status=status,
            provider_status=provider_status,
            payment_method=payment_method,
            card_network=brand_map.get(card.get("brand")),
            funding_type=funding_map.get(card.get("funding")),
            issuer_country=card.get("country"),
            failure_code=(failure_code or "stripe_payment_failed") if status == PaymentStatus.FAILED else None,
            failure_category=failure_category,
            failure_message=error.get("message") if status == PaymentStatus.FAILED else None,
            provider_failure_code=error.get("code") if status == PaymentStatus.FAILED else None,
            provider_failure_message=error.get("message") if status == PaymentStatus.FAILED else None,
            gross_amount=gross,
            processing_fee=processing_fee,
            provider_fee=Decimal("0"),
            other_cost=Decimal("0"),
            net_amount=net,
            refund_status=(RefundStatus.FULL if refund_amount == amount else RefundStatus.PARTIAL) if refund_amount else RefundStatus.NONE,
            refund_amount=refund_amount,
            dispute_status=DisputeStatus.OPEN if disputed else DisputeStatus.NONE,
            dispute_amount=dispute_amount,
            dispute_reason=dispute.get("reason"),
            settlement_date=None,
            settlement_currency=balance.get("currency", "").upper() or None,
            payout_reference=None,
            source_type=source,
            source_timestamp=now,
            raw_data_reference=raw_reference,
            data_availability={
                "settlement_date": DataAvailability.NOT_AVAILABLE,
                "provider_fee": DataAvailability.NOT_AVAILABLE,
                "payout_reference": DataAvailability.NOT_AVAILABLE,
                "card_details": DataAvailability.AVAILABLE if card else DataAvailability.NOT_AVAILABLE,
            },
            created_at_internal=now,
            updated_at_internal=now,
        )

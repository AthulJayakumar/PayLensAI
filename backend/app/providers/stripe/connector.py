"""Stripe Apps OAuth 2.0 and v1 PaymentIntent API adapter."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
import stripe

from app.providers.base import PaymentProviderConnector
from app.providers.models import OAuthTokenResponse, ProviderPage


def _stripe_dict(value) -> dict:
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if hasattr(value, "to_dict_recursive"):
        return value.to_dict_recursive()
    return dict(value)


class StripeTransport(ABC):
    @abstractmethod
    def exchange_token(self, developer_api_key: str, form: dict[str, str]) -> dict: ...

    @abstractmethod
    def list_payment_intents(self, access_token: str, params: dict) -> dict: ...

    @abstractmethod
    def retrieve_payment_intent(self, access_token: str, transaction_id: str) -> dict: ...

    def retrieve_charge(self, access_token: str, charge_id: str) -> dict:
        raise NotImplementedError

    def deauthorize(self, developer_api_key: str, client_id: str, stripe_user_id: str) -> dict:
        raise NotImplementedError


class OfficialStripeTransport(StripeTransport):
    def exchange_token(self, developer_api_key: str, form: dict[str, str]) -> dict:
        response = httpx.post(
            "https://api.stripe.com/v1/oauth/token",
            auth=(developer_api_key, ""),
            data=form,
            timeout=30,
        )
        response.raise_for_status()
        return response.json()

    def list_payment_intents(self, access_token: str, params: dict) -> dict:
        page = stripe.PaymentIntent.list(api_key=access_token, **params)
        return _stripe_dict(page)

    def retrieve_payment_intent(self, access_token: str, transaction_id: str) -> dict:
        item = stripe.PaymentIntent.retrieve(
            transaction_id,
            api_key=access_token,
            expand=["latest_charge.balance_transaction", "latest_charge.payment_method_details"],
        )
        return _stripe_dict(item)

    def retrieve_charge(self, access_token: str, charge_id: str) -> dict:
        item = stripe.Charge.retrieve(
            charge_id,
            api_key=access_token,
            expand=["balance_transaction", "payment_method_details"],
        )
        return _stripe_dict(item)

    def deauthorize(self, developer_api_key: str, client_id: str, stripe_user_id: str) -> dict:
        response = httpx.post(
            "https://api.stripe.com/v1/oauth/deauthorize",
            auth=(developer_api_key, ""),
            data={"client_id": client_id, "stripe_user_id": stripe_user_id},
            timeout=30,
        )
        response.raise_for_status()
        return response.json()


class StripeConnector(PaymentProviderConnector):
    provider = "STRIPE"
    authorization_endpoint = "https://marketplace.stripe.com/oauth/v2/authorize"

    def __init__(
        self,
        *,
        client_id: str,
        developer_api_key: str,
        transport: StripeTransport | None = None,
    ) -> None:
        if not client_id or not developer_api_key:
            raise ValueError("Stripe App client ID and developer API key are required.")
        self.client_id = client_id
        self.developer_api_key = developer_api_key
        self.transport = transport or OfficialStripeTransport()

    def authorize(self, *, state: str, redirect_uri: str) -> str:
        return f"{self.authorization_endpoint}?{urlencode({'client_id': self.client_id, 'redirect_uri': redirect_uri, 'state': state})}"

    def _tokens(self, payload: dict) -> OAuthTokenResponse:
        return OAuthTokenResponse(
            access_token=payload["access_token"],
            refresh_token=payload.get("refresh_token"),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            provider_account_id=payload["stripe_user_id"],
            scope=payload.get("scope"),
            livemode=bool(payload.get("livemode")),
        )

    def exchange_authorization_code(self, code: str) -> OAuthTokenResponse:
        return self._tokens(self.transport.exchange_token(
            self.developer_api_key, {"code": code, "grant_type": "authorization_code"}
        ))

    def refresh_credentials(self, refresh_token: str) -> OAuthTokenResponse:
        return self._tokens(self.transport.exchange_token(
            self.developer_api_key,
            {"refresh_token": refresh_token, "grant_type": "refresh_token"},
        ))

    def sync_historical(
        self,
        *,
        access_token: str,
        starting_after: str | None = None,
        created_after: datetime | None = None,
    ) -> ProviderPage:
        params: dict = {
            "limit": 100,
            "expand": ["data.latest_charge.balance_transaction", "data.latest_charge.payment_method_details"],
        }
        if starting_after:
            params["starting_after"] = starting_after
        if created_after:
            params["created"] = {"gte": int(created_after.timestamp())}
        payload = self.transport.list_payment_intents(access_token, params)
        objects = payload.get("data", [])
        return ProviderPage(
            objects=objects,
            has_more=bool(payload.get("has_more")),
            next_cursor=objects[-1]["id"] if payload.get("has_more") and objects else None,
        )

    def fetch_transaction(self, *, access_token: str, transaction_id: str) -> dict:
        return self.transport.retrieve_payment_intent(access_token, transaction_id)

    def fetch_charge(self, *, access_token: str, charge_id: str) -> dict:
        return self.transport.retrieve_charge(access_token, charge_id)

    def revoke(self, stripe_user_id: str) -> bool:
        result = self.transport.deauthorize(self.developer_api_key, self.client_id, stripe_user_id)
        return result.get("stripe_user_id") == stripe_user_id

    @staticmethod
    def verify_webhook(payload: bytes, signature: str, endpoint_secret: str) -> dict:
        event = stripe.Webhook.construct_event(payload, signature, endpoint_secret)
        return _stripe_dict(event)

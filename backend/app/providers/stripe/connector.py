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
    """Network boundary that allows Stripe calls to be replaced by test doubles."""
    @abstractmethod
    def exchange_token(self, developer_api_key: str, form: dict[str, str]) -> dict: ...

    @abstractmethod
    def list_payment_intents(self, access_token: str, params: dict) -> dict: ...

    @abstractmethod
    def retrieve_payment_intent(self, access_token: str, transaction_id: str) -> dict: ...

    def retrieve_charge(self, access_token: str, charge_id: str) -> dict:
        raise NotImplementedError

    def retrieve_account(self, access_token: str) -> dict:
        raise NotImplementedError

    def deauthorize(self, developer_api_key: str, client_id: str, stripe_user_id: str) -> dict:
        raise NotImplementedError


class OfficialStripeTransport(StripeTransport):
    """Concrete HTTP/SDK implementation used only when credentials are configured."""
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

    def retrieve_account(self, access_token: str) -> dict:
        account = stripe.Account.retrieve(api_key=access_token)
        return _stripe_dict(account)

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
    """Stripe Apps OAuth or private test-key PaymentIntent connector."""
    provider = "STRIPE"
    authorization_endpoint = "https://marketplace.stripe.com/oauth/v2/authorize"

    def __init__(
        self,
        *,
        client_id: str | None = None,
        developer_api_key: str | None = None,
        sandbox_api_key: str | None = None,
        sandbox_account_id: str | None = None,
        transport: StripeTransport | None = None,
    ) -> None:
        oauth_configured = bool(client_id and developer_api_key)
        sandbox_configured = bool(sandbox_api_key and sandbox_account_id)
        if oauth_configured == sandbox_configured:
            raise ValueError("Configure either Stripe App OAuth or one private sandbox key and account ID.")
        if sandbox_api_key and not sandbox_api_key.startswith("rk_test_"):
            raise ValueError("The private Stripe connector requires a restricted test key.")
        self.client_id = client_id
        self.developer_api_key = developer_api_key
        self.sandbox_api_key = sandbox_api_key
        self.sandbox_account_id = sandbox_account_id
        self.connection_mode = "SANDBOX_KEY" if sandbox_configured else "OAUTH"
        self.transport = transport or OfficialStripeTransport()

    def authorize(self, *, state: str, redirect_uri: str) -> str:
        if self.connection_mode != "OAUTH":
            raise ValueError("OAuth authorization is unavailable in private sandbox mode.")
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
        if self.connection_mode != "OAUTH":
            raise ValueError("OAuth token exchange is unavailable in private sandbox mode.")
        return self._tokens(self.transport.exchange_token(
            self.developer_api_key, {"code": code, "grant_type": "authorization_code"}
        ))

    def refresh_credentials(self, refresh_token: str) -> OAuthTokenResponse:
        if self.connection_mode != "OAUTH":
            raise ValueError("OAuth token refresh is unavailable in private sandbox mode.")
        return self._tokens(self.transport.exchange_token(
            self.developer_api_key,
            {"refresh_token": refresh_token, "grant_type": "refresh_token"},
        ))

    def verify_sandbox_credentials(self) -> OAuthTokenResponse:
        """Validate the server-held key and bind it to one expected test account."""
        if self.connection_mode != "SANDBOX_KEY" or not self.sandbox_api_key or not self.sandbox_account_id:
            raise ValueError("Private Stripe sandbox credentials are not configured.")
        account = self.transport.retrieve_account(self.sandbox_api_key)
        if account.get("id") != self.sandbox_account_id:
            raise ValueError("The Stripe sandbox key does not belong to the configured account.")
        return OAuthTokenResponse(
            access_token=self.sandbox_api_key,
            refresh_token=None,
            expires_at=None,
            provider_account_id=self.sandbox_account_id,
            scope="restricted_test_key",
            livemode=False,
        )

    def sync_historical(
        self,
        *,
        access_token: str,
        starting_after: str | None = None,
        created_after: datetime | None = None,
    ) -> ProviderPage:
        """Fetch one retry-safe page and expose the next Stripe cursor."""
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
        if self.connection_mode != "OAUTH":
            return False
        result = self.transport.deauthorize(self.developer_api_key, self.client_id, stripe_user_id)
        return result.get("stripe_user_id") == stripe_user_id

    @staticmethod
    def verify_webhook(payload: bytes, signature: str, endpoint_secret: str) -> dict:
        """Delegate exact-byte signature validation to Stripe's maintained SDK."""
        event = stripe.Webhook.construct_event(payload, signature, endpoint_secret)
        return _stripe_dict(event)

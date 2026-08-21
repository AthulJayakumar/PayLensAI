"""Capability-oriented connector contract; providers can opt into capabilities."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from app.providers.models import OAuthTokenResponse, ProviderPage, ReconciliationResult


class PaymentProviderConnector(ABC):
    provider: str

    @abstractmethod
    def authorize(self, *, state: str, redirect_uri: str) -> str:
        """Return a provider-hosted authorization URL."""

    @abstractmethod
    def exchange_authorization_code(self, code: str) -> OAuthTokenResponse:
        """Exchange a short-lived one-time authorization code."""

    @abstractmethod
    def refresh_credentials(self, refresh_token: str) -> OAuthTokenResponse:
        """Rotate provider access credentials."""

    @abstractmethod
    def sync_historical(
        self,
        *,
        access_token: str,
        starting_after: str | None = None,
        created_after: datetime | None = None,
    ) -> ProviderPage:
        """Fetch one retry-safe provider page."""

    @abstractmethod
    def fetch_transaction(self, *, access_token: str, transaction_id: str) -> dict:
        """Fetch one provider transaction."""

    def register_webhooks(self) -> str:
        """Return configuration state when registration is externally managed."""
        return "EXTERNALLY_CONFIGURED"

    def reconcile(self, *args, **kwargs) -> ReconciliationResult:
        raise NotImplementedError("This connector delegates reconciliation to PayLens.")

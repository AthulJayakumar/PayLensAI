"""Replaceable authenticated merchant context for local development."""

from __future__ import annotations

import hashlib
import hmac
import os
from abc import ABC, abstractmethod

from fastapi import Request
from pydantic import BaseModel, ConfigDict

from app.api.errors import APIError


class AuthenticatedMerchant(BaseModel):
    model_config = ConfigDict(extra="forbid")

    merchant_id: str
    name: str


class Authenticator(ABC):
    @abstractmethod
    def authenticate(self, request: Request) -> AuthenticatedMerchant:
        """Resolve a merchant from trusted authentication material."""


class DevelopmentApiKeyAuthenticator(Authenticator):
    """Local-only API-key auth whose identity cannot be selected by request parameters.

    The key must be at least 16 characters. Its SHA-256 digest becomes an opaque,
    stable merchant identifier; the raw key is never stored or logged.
    """

    header_name = "X-PayLens-Dev-Key"

    def __init__(self, *, expected_key: str | None = None, merchant_name: str | None = None) -> None:
        self.expected_digest = (
            hashlib.sha256(expected_key.encode()).digest() if expected_key else None
        )
        self.merchant_name = merchant_name or "Local PayLens Merchant"

    @classmethod
    def from_environment(cls) -> DevelopmentApiKeyAuthenticator:
        return cls(
            expected_key=os.environ.get("PAYLENS_DEV_API_KEY"),
            merchant_name=os.environ.get("PAYLENS_DEV_MERCHANT_NAME"),
        )

    def authenticate(self, request: Request) -> AuthenticatedMerchant:
        key = request.headers.get(self.header_name, "")
        if len(key) < 16:
            raise APIError(status_code=401, code="AUTHENTICATION_REQUIRED", message="A valid local development API key is required.")
        digest = hashlib.sha256(key.encode()).digest()
        if self.expected_digest is not None and not hmac.compare_digest(digest, self.expected_digest):
            raise APIError(status_code=401, code="INVALID_API_KEY", message="The local development API key is invalid.")
        return AuthenticatedMerchant(
            merchant_id=f"merchant_{hashlib.sha256(key.encode()).hexdigest()[:24]}",
            name=self.merchant_name,
        )


class StaticAuthenticator(Authenticator):
    """Deterministic test adapter; never selected by the production factory."""

    def __init__(self, merchant: AuthenticatedMerchant) -> None:
        self.merchant = merchant

    def authenticate(self, request: Request) -> AuthenticatedMerchant:
        return self.merchant

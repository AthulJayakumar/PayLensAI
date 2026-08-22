"""Replaceable authenticated merchant context for local development."""

from __future__ import annotations

import hashlib
import hmac
import os
from datetime import datetime, timezone
from abc import ABC, abstractmethod
from enum import StrEnum
from typing import Protocol

from fastapi import Request
import jwt
from jwt import PyJWKClient
from pydantic import BaseModel, ConfigDict

from app.api.errors import APIError


class MerchantRole(StrEnum):
    OWNER = "OWNER"
    ADMIN = "ADMIN"
    ANALYST = "ANALYST"
    VIEWER = "VIEWER"


class AuthenticatedMerchant(BaseModel):
    model_config = ConfigDict(extra="forbid")

    merchant_id: str
    name: str
    actor_id: str | None = None
    role: MerchantRole = MerchantRole.OWNER


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


class MembershipLookup(Protocol):
    def membership_for_subject(self, subject: str) -> tuple[str, str, MerchantRole] | None: ...


class CognitoAuthenticator(Authenticator):
    """Validate Cognito access tokens and resolve tenant membership server-side."""

    def __init__(self, *, region: str, user_pool_id: str, client_id: str, memberships: MembershipLookup) -> None:
        self.issuer = f"https://cognito-idp.{region}.amazonaws.com/{user_pool_id}"
        self.client_id = client_id
        self.memberships = memberships
        self.jwks = PyJWKClient(f"{self.issuer}/.well-known/jwks.json")

    def authenticate(self, request: Request) -> AuthenticatedMerchant:
        authorization = request.headers.get("Authorization", "")
        if not authorization.startswith("Bearer "):
            raise APIError(status_code=401, code="AUTHENTICATION_REQUIRED", message="A Cognito bearer token is required.")
        token = authorization.removeprefix("Bearer ").strip()
        try:
            signing_key = self.jwks.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                issuer=self.issuer,
                options={"require": ["exp", "iat", "iss", "sub", "token_use"]},
            )
            if claims.get("token_use") != "access" or claims.get("client_id") != self.client_id:
                raise ValueError("wrong token use or client")
            if datetime.fromtimestamp(int(claims["exp"]), timezone.utc) <= datetime.now(timezone.utc):
                raise ValueError("expired token")
        except Exception as error:
            raise APIError(status_code=401, code="INVALID_TOKEN", message="The Cognito token is invalid or expired.") from error
        membership = self.memberships.membership_for_subject(str(claims["sub"]))
        if membership is None:
            raise APIError(status_code=403, code="MEMBERSHIP_REQUIRED", message="The user has no active merchant membership.")
        merchant_id, merchant_name, role = membership
        return AuthenticatedMerchant(merchant_id=merchant_id, name=merchant_name, actor_id=str(claims["sub"]), role=role)

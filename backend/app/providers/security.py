"""Credential encryption and signed one-time OAuth state."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta, timezone

from cryptography.fernet import Fernet, InvalidToken


class CredentialCipher:
    def __init__(self, key: str) -> None:
        self._fernet = Fernet(key.encode())

    def encrypt(self, plaintext: str | None) -> str | None:
        return None if plaintext is None else self._fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, ciphertext: str | None) -> str | None:
        if ciphertext is None:
            return None
        try:
            return self._fernet.decrypt(ciphertext.encode()).decode()
        except InvalidToken as error:
            raise ValueError("Provider credential ciphertext is invalid.") from error


class CredentialVault:
    """Encrypt provider credentials before the persistence boundary."""

    def __init__(self, cipher: CredentialCipher, repository) -> None:
        self.cipher = cipher
        self.repository = repository

    def save(self, connection_id: str, access_token: str, refresh_token: str | None) -> None:
        self.repository.save_encrypted_credentials(
            connection_id,
            self.cipher.encrypt(access_token),
            self.cipher.encrypt(refresh_token),
        )

    def load(self, connection_id: str) -> tuple[str, str | None]:
        stored = self.repository.get_encrypted_credentials(connection_id)
        if stored is None:
            raise ValueError("Provider credentials are unavailable.")
        return self.cipher.decrypt(stored[0]), self.cipher.decrypt(stored[1])


class OAuthStateManager:
    def __init__(self, secret: str, state_repository, *, ttl: timedelta = timedelta(minutes=10)) -> None:
        if len(secret) < 32:
            raise ValueError("OAuth state secret must contain at least 32 characters.")
        self._secret = secret.encode()
        self._repository = state_repository
        self._ttl = ttl

    def issue(self, merchant_id: str) -> str:
        now = datetime.now(timezone.utc)
        nonce = secrets.token_urlsafe(24)
        payload = {"merchant_id": merchant_id, "nonce": nonce, "exp": int((now + self._ttl).timestamp())}
        encoded = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")
        signature = hmac.new(self._secret, encoded.encode(), hashlib.sha256).hexdigest()
        self._repository.store_oauth_state(hashlib.sha256(nonce.encode()).hexdigest(), merchant_id, now, now + self._ttl)
        return f"{encoded}.{signature}"

    def consume(self, state: str) -> str:
        try:
            encoded, supplied_signature = state.split(".", 1)
            expected = hmac.new(self._secret, encoded.encode(), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(expected, supplied_signature):
                raise ValueError
            padded = encoded + "=" * (-len(encoded) % 4)
            payload = json.loads(base64.urlsafe_b64decode(padded).decode())
            if int(payload["exp"]) < int(datetime.now(timezone.utc).timestamp()):
                raise ValueError
            nonce_hash = hashlib.sha256(payload["nonce"].encode()).hexdigest()
            if not self._repository.consume_oauth_state(nonce_hash, payload["merchant_id"]):
                raise ValueError
            return payload["merchant_id"]
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise ValueError("OAuth state is invalid, expired, or already used.") from error

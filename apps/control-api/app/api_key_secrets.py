"""Optional encrypted recovery for newly issued API-key plaintext secrets."""

from __future__ import annotations

import json
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from app.security import verify_api_secret
from app.settings import Settings


class ApiKeySecretConfigurationError(Exception):
    """The configured recovery key is missing or invalid."""


class ApiKeySecretCorruptError(Exception):
    """Stored ciphertext is invalid or does not match its API-key row."""


def _fernet(settings: Settings) -> Fernet | None:
    value = settings.api_key_encryption_key
    if not value:
        return None
    try:
        return Fernet(value.encode("ascii"))
    except (TypeError, UnicodeEncodeError, ValueError) as error:
        raise ApiKeySecretConfigurationError from error


def encryption_key_is_usable(settings: Settings) -> bool:
    try:
        return _fernet(settings) is not None
    except ApiKeySecretConfigurationError:
        return False


def encrypt_api_key_secret(
    *,
    key_id: str,
    organization_id: str,
    partner_app_id: str,
    plaintext: str,
    settings: Settings,
) -> str | None:
    fernet = _fernet(settings)
    if fernet is None:
        return None
    payload = {
        "key_id": key_id,
        "organization_id": organization_id,
        "partner_app_id": partner_app_id,
        "plaintext": plaintext,
    }
    encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return fernet.encrypt(encoded).decode("ascii")


def decrypt_api_key_secret(
    *,
    ciphertext: str,
    key_id: str,
    organization_id: str,
    partner_app_id: str,
    prefix: str,
    secret_hash: str,
    settings: Settings,
) -> str:
    fernet = _fernet(settings)
    if fernet is None:
        raise ApiKeySecretConfigurationError
    try:
        payload: Any = json.loads(fernet.decrypt(ciphertext.encode("ascii")))
    except (InvalidToken, UnicodeEncodeError, ValueError, TypeError) as error:
        raise ApiKeySecretCorruptError from error
    if not isinstance(payload, dict):
        raise ApiKeySecretCorruptError
    if any(
        payload.get(field) != expected
        for field, expected in {
            "key_id": key_id,
            "organization_id": organization_id,
            "partner_app_id": partner_app_id,
        }.items()
    ):
        raise ApiKeySecretCorruptError
    plaintext = payload.get("plaintext")
    if not isinstance(plaintext, str) or not plaintext.startswith("agw_live_"):
        raise ApiKeySecretCorruptError
    try:
        key_prefix, secret = plaintext.removeprefix("agw_live_").split("_", 1)
    except ValueError as error:
        raise ApiKeySecretCorruptError from error
    if key_prefix != prefix or not verify_api_secret(secret, secret_hash, settings):
        raise ApiKeySecretCorruptError
    return plaintext

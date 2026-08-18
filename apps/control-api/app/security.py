"""Password, API-key, and short-lived realtime-token helpers."""

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta

from argon2 import PasswordHasher
from itsdangerous import BadSignature, URLSafeTimedSerializer

from app.settings import Settings

password_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return password_hasher.verify(password_hash, password)
    except Exception:
        return False


def issue_api_key() -> tuple[str, str, str]:
    prefix = secrets.token_hex(5)
    secret = secrets.token_urlsafe(32)
    return f"agw_live_{prefix}_{secret}", prefix, secret


def hash_api_secret(secret: str, settings: Settings) -> str:
    return hmac.new(settings.api_key_pepper.encode(), secret.encode(), hashlib.sha256).hexdigest()


def verify_api_secret(secret: str, expected_hash: str, settings: Settings) -> bool:
    return hmac.compare_digest(hash_api_secret(secret, settings), expected_hash)


def token_serializer(settings: Settings) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.session_secret, salt="gateway-realtime-v1")


def issue_realtime_token(subject: dict[str, str], settings: Settings) -> str:
    payload = {
        **subject,
        "issuer": settings.realtime_issuer,
        "expires_at": (datetime.now(UTC) + timedelta(minutes=5)).isoformat(),
    }
    return token_serializer(settings).dumps(payload)


def verify_realtime_token(token: str, settings: Settings) -> dict[str, str] | None:
    try:
        payload = token_serializer(settings).loads(token, max_age=300)
    except BadSignature:
        return None
    return payload if payload.get("issuer") == settings.realtime_issuer else None


def timestamp_expired(value: datetime | None) -> bool:
    if value is None:
        return False
    comparable = value if value.tzinfo else value.replace(tzinfo=UTC)
    return comparable <= datetime.now(UTC)

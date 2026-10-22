"""API-key authentication shared by realtime exchange and customer reads."""

from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_session
from app.models import ApiKey, PartnerApp
from app.security import timestamp_expired, verify_api_secret
from app.settings import get_settings


@dataclass(frozen=True, slots=True)
class PartnerIdentity:
    organization_id: str
    partner_app_id: str
    key_id: str
    prefix: str
    agent_slug: str
    scopes: frozenset[str]


def authenticate_api_key(authorization: str | None, session: Session) -> PartnerIdentity:
    if not authorization or not authorization.startswith("Bearer agw_live_"):
        raise HTTPException(status_code=401, detail="Bearer API key required")
    parts = authorization.removeprefix("Bearer ").split("_", 3)
    if len(parts) != 4:
        raise HTTPException(status_code=401, detail="Malformed API key")
    key = session.scalar(select(ApiKey).where(ApiKey.prefix == parts[2]))
    if (
        not key or key.revoked_at or timestamp_expired(key.expires_at)
        or not verify_api_secret(parts[3], key.secret_hash, get_settings())
    ):
        raise HTTPException(status_code=401, detail="Invalid API key")
    app = session.get(PartnerApp, key.partner_app_id)
    if (
        not app
        or not app.enabled
        or app.deleted_at is not None
        or app.organization_id != key.organization_id
    ):
        raise HTTPException(status_code=403, detail="Partner application disabled")
    # An app scope reduction also applies immediately to existing keys.
    scopes = frozenset(key.scopes.split(",")) & frozenset(app.scopes.split(","))
    key.last_used_at = datetime.now(UTC)
    session.commit()
    return PartnerIdentity(
        key.organization_id, app.id, key.id, key.prefix, app.agent_slug, scopes
    )


def require_call_reader(
    authorization: str | None = Header(default=None),
    session: Session = Depends(get_session),
) -> PartnerIdentity:
    identity = authenticate_api_key(authorization, session)
    if "calls:read" not in identity.scopes:
        raise HTTPException(status_code=403, detail="calls:read scope required")
    return identity

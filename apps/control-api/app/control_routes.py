"""Tenant-scoped browser and machine control-plane endpoints."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit_log import audit
from app.auth import Principal, require_principal, require_role
from app.database import get_session
from app.destination_policy import validate_entry
from app.models import ApiKey, PartnerApp
from app.rate_limits import enforce_token_rate_limit
from app.security import (
    hash_api_secret,
    issue_api_key,
    issue_realtime_token,
    timestamp_expired,
    verify_api_secret,
)
from app.settings import get_settings

router = APIRouter(tags=["control"])
settings = get_settings()
ALLOWED_SCOPES = {
    "calls:read",
    "media:stream",
    "media:control",
    "calls:dtmf",
    "calls:hold",
    "calls:mute",
    "calls:hangup",
    "calls:transfer",
    "calls:route",
    "calls:dialplan",
    "calls:originate",
    "media:playback",
    "channel:variables",
}


class AppRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    agent_slug: str = Field(pattern=r"^[a-z0-9-]{3,80}$")
    scopes: list[str] = ["calls:read", "media:stream"]
    allowed_destinations: list[str] = []


class KeyRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    scopes: list[str] = ["calls:read", "media:stream"]
    expires_at: datetime | None = None


def validate_scopes(scopes: list[str]) -> list[str]:
    normalized = sorted(set(scopes))
    unsupported = set(normalized) - ALLOWED_SCOPES
    if unsupported:
        raise HTTPException(status_code=422, detail=f"Unsupported scopes: {sorted(unsupported)}")
    return normalized


def validate_destinations(destinations: list[str]) -> list[str]:
    normalized = sorted(set(destinations))
    if len(normalized) > 100:
        raise HTTPException(status_code=422, detail="At most 100 destinations are allowed")
    for entry in normalized:
        try:
            validate_entry(entry)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
    return normalized


def serialize_app(app: PartnerApp) -> dict[str, object]:
    return {
        "id": app.id,
        "organization_id": app.organization_id,
        "name": app.name,
        "agent_slug": app.agent_slug,
        "enabled": app.enabled,
        "scopes": app.scopes.split(",") if app.scopes else [],
        "allowed_destinations": (
            app.allowed_destinations.split(",") if app.allowed_destinations else []
        ),
        "created_at": app.created_at,
    }


@router.get("/organizations/{organization_id}/partner-apps", response_model=None)
def list_partner_apps(
    organization_id: str,
    principal: Principal = Depends(require_principal),
    session: Session = Depends(get_session),
) -> list[dict[str, object]]:
    if organization_id != principal.organization_id:
        raise HTTPException(status_code=404, detail="Organization not found")
    apps = session.scalars(
        select(PartnerApp).where(PartnerApp.organization_id == organization_id)
    )
    return [serialize_app(app) for app in apps]


@router.post("/organizations/{organization_id}/partner-apps", status_code=201, response_model=None)
def create_partner_app(
    payload: AppRequest,
    organization_id: str,
    principal: Principal = Depends(require_role("owner", "admin", "developer")),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    if organization_id != principal.organization_id:
        raise HTTPException(status_code=404, detail="Organization not found")
    scopes = validate_scopes(payload.scopes)
    duplicate = session.scalar(select(PartnerApp).where(PartnerApp.agent_slug == payload.agent_slug))
    if duplicate:
        raise HTTPException(status_code=409, detail="Agent slug is already in use")
    app = PartnerApp(
        organization_id=organization_id,
        name=payload.name,
        agent_slug=payload.agent_slug,
        scopes=",".join(scopes),
        allowed_destinations=",".join(validate_destinations(payload.allowed_destinations)),
    )
    session.add(app)
    session.flush()
    audit(session, principal, "partner_app.created", app.id)
    session.commit()
    return serialize_app(app)


@router.post("/partner-apps/{app_id}/api-keys", status_code=201)
def create_key(
    payload: KeyRequest,
    app_id: str,
    principal: Principal = Depends(require_role("owner", "admin", "developer")),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    app = session.scalar(
        select(PartnerApp).where(
            PartnerApp.id == app_id, PartnerApp.organization_id == principal.organization_id
        )
    )
    if not app:
        raise HTTPException(status_code=404, detail="Partner application not found")
    scopes = validate_scopes(payload.scopes)
    app_scopes = set(app.scopes.split(","))
    if not set(scopes).issubset(app_scopes):
        raise HTTPException(status_code=422, detail="Key scopes must be a subset of app scopes")
    if payload.expires_at and (
        payload.expires_at.tzinfo is None or payload.expires_at <= datetime.now(UTC)
    ):
        raise HTTPException(status_code=422, detail="Key expiry must be a future UTC timestamp")
    plaintext, prefix, secret = issue_api_key()
    key = ApiKey(
        organization_id=app.organization_id,
        partner_app_id=app.id,
        name=payload.name,
        prefix=prefix,
        secret_hash=hash_api_secret(secret, settings),
        scopes=",".join(scopes),
        expires_at=payload.expires_at,
    )
    session.add(key)
    session.flush()
    audit(session, principal, "api_key.created", key.id)
    session.commit()
    return {"id": key.id, "prefix": key.prefix, "key": plaintext, "scopes": scopes}


@router.delete("/api-keys/{key_id}", status_code=204)
def revoke_key(
    key_id: str,
    principal: Principal = Depends(require_role("owner", "admin", "developer")),
    session: Session = Depends(get_session),
) -> Response:
    key = session.scalar(
        select(ApiKey).where(
            ApiKey.id == key_id, ApiKey.organization_id == principal.organization_id
        )
    )
    if not key:
        raise HTTPException(status_code=404, detail="API key not found")
    key.revoked_at = datetime.now(UTC)
    audit(session, principal, "api_key.revoked", key.id)
    session.commit()
    return Response(status_code=204)


@router.post("/realtime/tokens")
def create_realtime_token(
    request: Request,
    authorization: str = Header(),
    session: Session = Depends(get_session),
) -> dict[str, str]:
    if not authorization.startswith("Bearer agw_live_"):
        raise HTTPException(status_code=401, detail="Bearer API key required")
    parts = authorization.removeprefix("Bearer ").split("_", 3)
    if len(parts) != 4:
        raise HTTPException(status_code=401, detail="Malformed API key")
    key = session.scalar(select(ApiKey).where(ApiKey.prefix == parts[2]))
    invalid = not key or key.revoked_at or (key and timestamp_expired(key.expires_at))
    if invalid or not verify_api_secret(parts[3], key.secret_hash, settings):
        raise HTTPException(status_code=401, detail="Invalid API key")
    app = session.get(PartnerApp, key.partner_app_id)
    if not app or not app.enabled:
        raise HTTPException(status_code=403, detail="Partner application disabled")
    enforce_token_rate_limit(request, settings, key.prefix, key.organization_id)
    key.last_used_at = datetime.now(UTC)
    session.commit()
    subject = {
        "api_key_id": key.id,
        "organization_id": key.organization_id,
        "partner_app_id": app.id,
        "agent_slug": app.agent_slug,
        "scopes": key.scopes,
    }
    return {"token": issue_realtime_token(subject, settings), "expires_in": "300"}

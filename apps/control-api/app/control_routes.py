"""Tenant-scoped browser and machine control-plane endpoints."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import Principal, create_session, require_principal, require_role
from app.database import get_session
from app.models import ApiKey, AuditEvent, Membership, PartnerApp, User
from app.security import (
    hash_api_secret,
    issue_api_key,
    issue_realtime_token,
    verify_api_secret,
    verify_password,
)
from app.settings import get_settings

router = APIRouter(tags=["control"])
settings = get_settings()


class LoginRequest(BaseModel):
    email: str
    password: str = Field(min_length=12)


class AppRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    agent_slug: str = Field(pattern=r"^[a-z0-9-]{3,80}$")
    scopes: list[str] = ["calls:read", "media:stream"]


class KeyRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    scopes: list[str] = ["calls:read", "media:stream"]


def audit(session: Session, principal: Principal | None, action: str, target_id: str | None) -> None:
    if principal:
        session.add(AuditEvent(organization_id=principal.organization_id, actor_id=principal.user_id, action=action, target_id=target_id))


@router.post("/auth/login")
def login(payload: LoginRequest, response: Response, session: Session = Depends(get_session)) -> dict[str, str]:
    user = session.scalar(select(User).where(User.email == payload.email.lower()))
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    membership = session.scalar(select(Membership).where(Membership.user_id == user.id))
    if not membership:
        raise HTTPException(status_code=403, detail="No organization membership")
    principal = Principal(user.id, membership.organization_id, membership.role)
    response.set_cookie("gateway_session", create_session(principal), httponly=True, samesite="strict", secure=False)
    audit(session, principal, "auth.login", user.id)
    session.commit()
    return {"organization_id": principal.organization_id, "role": principal.role}


@router.post("/auth/logout", status_code=204)
def logout(response: Response) -> Response:
    response.delete_cookie("gateway_session")
    return response


@router.get("/auth/session")
def browser_session(principal: Principal = Depends(require_principal)) -> Principal:
    return principal


@router.get("/organizations/{organization_id}/partner-apps")
def list_partner_apps(organization_id: str, principal: Principal = Depends(require_principal), session: Session = Depends(get_session)) -> list[PartnerApp]:
    if organization_id != principal.organization_id:
        raise HTTPException(status_code=404, detail="Organization not found")
    return list(session.scalars(select(PartnerApp).where(PartnerApp.organization_id == organization_id)))


@router.post("/organizations/{organization_id}/partner-apps", status_code=201)
def create_partner_app(payload: AppRequest, organization_id: str, principal: Principal = Depends(require_role("owner", "admin", "developer")), session: Session = Depends(get_session)) -> PartnerApp:
    if organization_id != principal.organization_id:
        raise HTTPException(status_code=404, detail="Organization not found")
    app = PartnerApp(organization_id=organization_id, name=payload.name, agent_slug=payload.agent_slug, scopes=",".join(payload.scopes))
    session.add(app)
    audit(session, principal, "partner_app.created", app.id)
    session.commit()
    return app


@router.post("/partner-apps/{app_id}/api-keys", status_code=201)
def create_key(payload: KeyRequest, app_id: str, principal: Principal = Depends(require_role("owner", "admin", "developer")), session: Session = Depends(get_session)) -> dict[str, object]:
    app = session.scalar(select(PartnerApp).where(PartnerApp.id == app_id, PartnerApp.organization_id == principal.organization_id))
    if not app:
        raise HTTPException(status_code=404, detail="Partner application not found")
    plaintext, prefix, secret = issue_api_key()
    key = ApiKey(organization_id=app.organization_id, partner_app_id=app.id, name=payload.name, prefix=prefix, secret_hash=hash_api_secret(secret, settings), scopes=",".join(payload.scopes))
    session.add(key)
    audit(session, principal, "api_key.created", key.id)
    session.commit()
    return {"id": key.id, "prefix": key.prefix, "key": plaintext, "scopes": payload.scopes}


@router.delete("/api-keys/{key_id}", status_code=204)
def revoke_key(key_id: str, principal: Principal = Depends(require_role("owner", "admin", "developer")), session: Session = Depends(get_session)) -> Response:
    key = session.scalar(select(ApiKey).where(ApiKey.id == key_id, ApiKey.organization_id == principal.organization_id))
    if not key:
        raise HTTPException(status_code=404, detail="API key not found")
    key.revoked_at = datetime.now(UTC)
    audit(session, principal, "api_key.revoked", key.id)
    session.commit()
    return Response(status_code=204)


@router.post("/realtime/tokens")
def create_realtime_token(authorization: str = Header(), session: Session = Depends(get_session)) -> dict[str, str]:
    if not authorization.startswith("Bearer agw_live_"):
        raise HTTPException(status_code=401, detail="Bearer API key required")
    parts = authorization.removeprefix("Bearer ").split("_", 3)
    if len(parts) != 4:
        raise HTTPException(status_code=401, detail="Malformed API key")
    key = session.scalar(select(ApiKey).where(ApiKey.prefix == parts[2]))
    invalid = not key or key.revoked_at or (key.expires_at and key.expires_at <= datetime.now(UTC))
    if invalid or not verify_api_secret(parts[3], key.secret_hash, settings):
        raise HTTPException(status_code=401, detail="Invalid API key")
    app = session.get(PartnerApp, key.partner_app_id)
    if not app or not app.enabled:
        raise HTTPException(status_code=403, detail="Partner application disabled")
    key.last_used_at = datetime.now(UTC)
    session.commit()
    subject = {"organization_id": key.organization_id, "partner_app_id": app.id, "agent_slug": app.agent_slug, "scopes": key.scopes}
    return {"token": issue_realtime_token(subject, settings), "expires_in": "300"}

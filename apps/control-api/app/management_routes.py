"""Dashboard read/update endpoints with tenant-safe response shapes."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.api_key_secrets import encryption_key_is_usable
from app.audit_log import audit
from app.auth import Principal, require_principal, require_role
from app.control_routes import serialize_app, validate_destinations, validate_scopes
from app.database import get_session
from app.models import ApiKey, AuditEvent, PartnerApp
from app.security import timestamp_expired
from app.settings import get_settings

router = APIRouter(tags=["management"])


class AppUpdate(BaseModel):
    name: str | None = None
    enabled: bool | None = None
    scopes: list[str] | None = None
    allowed_destinations: list[str] | None = None


@router.patch("/partner-apps/{app_id}")
def update_partner_app(
    app_id: str,
    payload: AppUpdate,
    principal: Principal = Depends(require_role("owner", "admin", "developer")),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    app = session.scalar(
        select(PartnerApp).where(
            PartnerApp.id == app_id,
            PartnerApp.organization_id == principal.organization_id,
            PartnerApp.deleted_at.is_(None),
        )
    )
    if not app:
        raise HTTPException(status_code=404, detail="Partner application not found")
    if payload.name is not None:
        name = payload.name.strip()
        if not name or len(name) > 120:
            raise HTTPException(status_code=422, detail="App name must contain 1-120 characters")
        app.name = name
    if payload.enabled is not None:
        app.enabled = payload.enabled
    if payload.scopes is not None:
        app.scopes = ",".join(validate_scopes(payload.scopes))
    if payload.allowed_destinations is not None:
        app.allowed_destinations = ",".join(validate_destinations(payload.allowed_destinations))
    audit(session, principal, "partner_app.updated", app.id)
    session.commit()
    return serialize_app(app)


@router.get("/partner-apps/{app_id}/api-keys")
def list_api_keys(
    app_id: str,
    principal: Principal = Depends(require_principal),
    session: Session = Depends(get_session),
) -> list[dict[str, object]]:
    app = session.scalar(
        select(PartnerApp).where(
            PartnerApp.id == app_id,
            PartnerApp.organization_id == principal.organization_id,
            PartnerApp.deleted_at.is_(None),
        )
    )
    if not app:
        raise HTTPException(status_code=404, detail="Partner application not found")
    settings = get_settings()
    keys = session.scalars(select(ApiKey).where(ApiKey.partner_app_id == app.id))
    return [
        {
            "id": key.id,
            "name": key.name,
            "prefix": key.prefix,
            "scopes": key.scopes.split(","),
            "created_at": key.created_at,
            "last_used_at": key.last_used_at,
            "revoked_at": key.revoked_at,
            "expires_at": key.expires_at,
            "copy_available": bool(
                key.encrypted_secret
                and key.revoked_at is None
                and not timestamp_expired(key.expires_at)
                and app.enabled
                and encryption_key_is_usable(settings)
            ),
        }
        for key in keys
    ]


@router.get("/audit-events")
def list_audit_events(
    principal: Principal = Depends(require_principal),
    session: Session = Depends(get_session),
) -> list[dict[str, object]]:
    events = session.scalars(
        select(AuditEvent)
        .where(AuditEvent.organization_id == principal.organization_id)
        .order_by(AuditEvent.created_at.desc())
        .limit(100)
    )
    return [
        {
            "id": event.id,
            "action": event.action,
            "actor_id": event.actor_id,
            "target_id": event.target_id,
            "created_at": event.created_at,
        }
        for event in events
    ]


@router.delete("/partner-apps/{app_id}", status_code=204)
def disable_partner_app(
    app_id: str,
    principal: Principal = Depends(require_role("owner", "admin")),
    session: Session = Depends(get_session),
) -> Response:
    app = session.scalar(
        select(PartnerApp).where(
            PartnerApp.id == app_id,
            PartnerApp.organization_id == principal.organization_id,
        ).with_for_update()
    )
    if not app:
        raise HTTPException(status_code=404, detail="Partner application not found")
    if app.deleted_at is not None:
        return Response(status_code=204)
    if session.scalar(
        select(ApiKey.id)
        .where(ApiKey.partner_app_id == app.id, ApiKey.revoked_at.is_(None))
        .limit(1)
    ):
        raise HTTPException(
            status_code=409,
            detail="Revoke all active API keys before deleting this Partner App",
        )
    deleted_at = datetime.now(UTC)
    app.deleted_at = deleted_at
    app.enabled = False
    session.execute(
        update(ApiKey)
        .where(ApiKey.partner_app_id == app.id)
        .values(encrypted_secret=None)
    )
    session.execute(
        update(ApiKey)
        .where(ApiKey.partner_app_id == app.id, ApiKey.revoked_at.is_(None))
        .values(revoked_at=deleted_at)
    )
    audit(session, principal, "partner_app.deleted", app.id)
    session.commit()
    return Response(status_code=204)

"""Tenant-scoped Asterisk, member, connection, and active-call views."""

from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import Principal, require_principal
from app.database import get_session
from app.models import Membership, User
from app.realtime_registry import registry
from app.settings import get_settings

router = APIRouter(tags=["runtime"])


def tenant_connections(principal: Principal) -> set[str]:
    return {
        item.id
        for item in registry.connections.values()
        if item.organization_id == principal.organization_id
    }


@router.get("/asterisk")
def asterisk_configuration(
    principal: Principal = Depends(require_principal),
) -> dict[str, object]:
    settings = get_settings()
    parsed = urlparse(settings.ari_base_url or "")
    return {
        "configured": bool(
            settings.ari_base_url and settings.ari_username and settings.ari_password
        ),
        "host": parsed.hostname,
        "ari_port": parsed.port,
        "stasis_app": "asterisk-ai-gateway",
        "media_transport": settings.media_transport,
        "audiosocket_port": settings.audiosocket_port,
        "audiosocket_advertise_host": settings.audiosocket_advertise_host,
        "credentials": "configured" if settings.ari_username else "missing",
        "organization_id": principal.organization_id,
    }


@router.get("/runtime")
def runtime(
    request: Request, principal: Principal = Depends(require_principal)
) -> dict[str, object]:
    connection_ids = tenant_connections(principal)
    return {
        "active_connections": len(connection_ids),
        "active_calls": sum(
            call.connection_id in connection_ids for call in registry.calls.values()
        ),
        "ari_connected": bool(getattr(request.app.state.ari_listener, "ready", False)),
        "audiosocket_listening": bool(
            getattr(request.app.state.audio_server, "server", None)
        ),
    }


@router.get("/connections")
def connections(
    principal: Principal = Depends(require_principal),
) -> list[dict[str, object]]:
    return [
        {
            "id": item.id,
            "partner_app_id": item.partner_app_id,
            "agent_slug": item.agent_slug,
            "scopes": sorted(item.scopes),
        }
        for item in registry.connections.values()
        if item.organization_id == principal.organization_id
    ]


@router.get("/calls")
def calls(
    principal: Principal = Depends(require_principal),
) -> list[dict[str, object]]:
    connection_ids = tenant_connections(principal)
    return [
        {
            "id": call.id,
            "agent_slug": call.agent_slug,
            "media_transport": call.media_transport,
            "transfer_consulting": bool(call.transfer_channel_id),
        }
        for call in registry.calls.values()
        if call.connection_id in connection_ids
    ]


@router.get("/organization/members")
def members(
    principal: Principal = Depends(require_principal),
    session: Session = Depends(get_session),
) -> list[dict[str, str]]:
    rows = session.execute(
        select(Membership, User)
        .join(User, User.id == Membership.user_id)
        .where(Membership.organization_id == principal.organization_id)
    )
    return [
        {"user_id": membership.user_id, "email": user.email, "role": membership.role}
        for membership, user in rows
    ]

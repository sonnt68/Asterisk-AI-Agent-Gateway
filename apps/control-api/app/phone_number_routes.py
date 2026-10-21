"""Tenant-safe exact phone-number to Partner App mapping endpoints."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.audit_log import audit
from app.auth import Principal, require_principal
from app.database import get_session
from app.freepbx_client import BridgeError
from app.models import PartnerApp, PhoneNumber
from app.outbound_number_policy import outbound_apps_for_phone, replace_outbound_apps
from app.telephony import managed_route_id
from app.telephony_access import bridge_client, bridge_http_error, require_operator_manager
from app.telephony_schemas import PhoneNumberCreate, PhoneNumberPatch

router = APIRouter(tags=["phone-numbers"])


def _rows(session: Session, organization_id: str) -> list[tuple[PhoneNumber, PartnerApp]]:
    return list(
        session.execute(
            select(PhoneNumber, PartnerApp)
            .join(PartnerApp, PartnerApp.id == PhoneNumber.partner_app_id)
            .where(
                PhoneNumber.organization_id == organization_id,
                PartnerApp.organization_id == PhoneNumber.organization_id,
            )
            .order_by(PhoneNumber.number)
        )
    )


def serialize_phone_number(
    phone: PhoneNumber,
    app: PartnerApp,
    outbound_apps: list[PartnerApp] | None = None,
) -> dict[str, object]:
    outbound_apps = outbound_apps or []
    return {
        "id": phone.id,
        "number": phone.number,
        "label": phone.label,
        "partner_app_id": app.id,
        "partner_app_name": app.name,
        "agent_slug": app.agent_slug,
        "outbound_partner_apps": [
            {
                "id": outbound.id,
                "name": outbound.name,
                "agent_slug": outbound.agent_slug,
                "enabled": outbound.enabled,
            }
            for outbound in outbound_apps
        ],
        "outbound_partner_app_ids": [outbound.id for outbound in outbound_apps],
        "enabled": phone.enabled,
        "pbx_applied": phone.pbx_applied,
        "created_at": phone.created_at,
        "updated_at": phone.updated_at,
    }


def _did_success(value: object, route_id: str, number: str) -> bool:
    data = value.get("route", value) if isinstance(value, dict) else value
    if not isinstance(data, dict):
        return False
    return data.get("route_id") == route_id and data.get("number") == number


@router.get("/phone-numbers")
def list_phone_numbers(
    principal: Principal = Depends(require_principal),
    session: Session = Depends(get_session),
) -> list[dict[str, object]]:
    require_operator_manager(principal)
    return [
        serialize_phone_number(
            phone,
            app,
            outbound_apps_for_phone(session, phone.id, principal.organization_id),
        )
        for phone, app in _rows(session, principal.organization_id)
    ]


@router.post("/phone-numbers", status_code=201)
async def create_phone_number(
    payload: PhoneNumberCreate,
    principal: Principal = Depends(require_principal),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    settings = require_operator_manager(principal)
    app = session.scalar(
        select(PartnerApp).where(
            PartnerApp.id == payload.partner_app_id,
            PartnerApp.organization_id == principal.organization_id,
            PartnerApp.enabled.is_(True),
        )
    )
    if not app:
        raise HTTPException(status_code=422, detail="Partner application is not enabled")
    route_id = managed_route_id(principal.organization_id, payload.number)
    phone = PhoneNumber(
        id=route_id,
        organization_id=principal.organization_id,
        partner_app_id=app.id,
        number=payload.number,
        label=payload.label,
        enabled=payload.enabled,
        pbx_applied=False,
    )
    session.add(phone)
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        raise HTTPException(status_code=409, detail="Phone number is already mapped") from None
    try:
        outbound_apps = replace_outbound_apps(
            session,
            phone,
            principal.organization_id,
            payload.outbound_partner_app_ids,
        )
    except ValueError as error:
        session.rollback()
        raise HTTPException(status_code=422, detail=str(error)) from None
    try:
        result = await bridge_client(settings).save_did(
            {"route_id": route_id, "number": payload.number, "label": payload.label}
        )
    except BridgeError as error:
        session.rollback()
        raise bridge_http_error(error) from None
    if not _did_success(result, route_id, payload.number):
        session.rollback()
        raise bridge_http_error()
    audit(session, principal, "phone_number.created", phone.id)
    if payload.outbound_partner_app_ids:
        audit(session, principal, "phone_number.outbound_apps.updated", phone.id)
    session.commit()
    return serialize_phone_number(phone, app, outbound_apps)


@router.patch("/phone-numbers/{phone_id}")
def update_phone_number(
    phone_id: str,
    payload: PhoneNumberPatch,
    principal: Principal = Depends(require_principal),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    require_operator_manager(principal)
    phone = session.scalar(
        select(PhoneNumber).where(
            PhoneNumber.id == phone_id,
            PhoneNumber.organization_id == principal.organization_id,
        )
    )
    if not phone:
        raise HTTPException(status_code=404, detail="Phone number not found")
    current_app = session.scalar(
        select(PartnerApp).where(
            PartnerApp.id == phone.partner_app_id,
            PartnerApp.organization_id == principal.organization_id,
        )
    )
    target_app_id = payload.partner_app_id or phone.partner_app_id
    effective_enabled = payload.enabled if payload.enabled is not None else phone.enabled
    if target_app_id == phone.partner_app_id and effective_enabled is False and current_app:
        app = current_app
    else:
        app = session.scalar(
            select(PartnerApp).where(
                PartnerApp.id == target_app_id,
                PartnerApp.organization_id == principal.organization_id,
                PartnerApp.enabled.is_(True),
            )
        )
    if not app:
        raise HTTPException(status_code=422, detail="Partner application is not enabled")
    if payload.outbound_partner_app_ids is None:
        outbound_apps = outbound_apps_for_phone(
            session, phone.id, principal.organization_id
        )
    else:
        try:
            outbound_apps = replace_outbound_apps(
                session,
                phone,
                principal.organization_id,
                payload.outbound_partner_app_ids,
            )
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from None
    phone.partner_app_id = app.id
    if payload.label is not None:
        phone.label = payload.label
    if payload.enabled is not None:
        phone.enabled = payload.enabled
    phone.updated_at = datetime.now(UTC)
    audit(session, principal, "phone_number.updated", phone.id)
    if payload.outbound_partner_app_ids is not None:
        audit(session, principal, "phone_number.outbound_apps.updated", phone.id)
    session.commit()
    return serialize_phone_number(phone, app, outbound_apps)

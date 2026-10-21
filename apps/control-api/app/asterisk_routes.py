"""Owner/Admin PBX provisioning, trunk, and explicit apply endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit_log import audit
from app.auth import Principal, require_principal
from app.database import get_session
from app.freepbx_client import BridgeError
from app.models import PhoneNumber
from app.realtime_registry import registry
from app.settings import get_settings
from app.telephony_access import (
    bridge_client,
    bridge_http_error,
    bridge_unavailable_error,
    ensure_trunk_editable,
    is_operator_manager,
    require_operator_manager,
    sanitize_trunk,
    trunk_payload,
)
from app.telephony_schemas import TrunkCreate, TrunkPatch

router = APIRouter(tags=["asterisk"])


def _trunk_id(value: str) -> str:
    if not value or len(value) > 120 or any(char in value for char in ("\x00", "\r", "\n")):
        raise HTTPException(status_code=422, detail="Invalid trunk id")
    return value


@router.get("/asterisk/provisioning")
async def provisioning_status(
    principal: Principal = Depends(require_principal),
) -> dict[str, object]:
    settings = get_settings()
    if not is_operator_manager(principal, settings):
        return {
            "configured": False,
            "can_manage": False,
            "connected": False,
            "needs_apply": False,
            "transports": [],
        }
    client = bridge_client(settings)
    result: dict[str, object] = {
        "configured": client.configured,
        "can_manage": True,
        "connected": False,
        "needs_apply": False,
        "transports": [],
    }
    if not client.configured:
        result["error"] = "FreePBX bridge is not configured"
        return result
    try:
        data = await client.status()
    except BridgeError as error:
        result["error"] = str(error)
        return result
    if not isinstance(data, dict):
        result["error"] = "FreePBX bridge returned an invalid status"
        return result
    result["connected"] = bool(data.get("connected", True))
    result["needs_apply"] = bool(data.get("needs_apply", False))
    transports = data.get("transports", [])
    if isinstance(transports, list):
        result["transports"] = [item for item in transports if isinstance(item, str)]
    return result


@router.get("/asterisk/trunks")
async def list_trunks(
    principal: Principal = Depends(require_principal),
) -> list[dict[str, object]]:
    settings = require_operator_manager(principal)
    client = bridge_client(settings)
    try:
        data = await client.list_trunks()
    except BridgeError as error:
        if "not configured" in str(error):
            raise bridge_unavailable_error() from None
        raise bridge_http_error(error) from None
    rows = data.get("trunks", data) if isinstance(data, dict) else data
    if not isinstance(rows, list):
        raise bridge_http_error()
    return [sanitize_trunk(row) for row in rows]


@router.post("/asterisk/trunks", status_code=201)
async def create_trunk(
    payload: TrunkCreate,
    principal: Principal = Depends(require_principal),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    settings = require_operator_manager(principal)
    try:
        data = await bridge_client(settings).save_trunk(trunk_payload(payload))
    except BridgeError as error:
        raise bridge_http_error(error) from None
    trunk = sanitize_trunk(data)
    if not trunk["id"]:
        raise bridge_http_error()
    audit(session, principal, "asterisk_trunk.created", str(trunk["id"]))
    session.commit()
    return trunk


@router.patch("/asterisk/trunks/{trunk_id}")
async def update_trunk(
    trunk_id: str,
    payload: TrunkPatch,
    principal: Principal = Depends(require_principal),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    settings = require_operator_manager(principal)
    trunk_id = _trunk_id(trunk_id)
    body = trunk_payload(payload, include_unset=True)
    client = bridge_client(settings)
    try:
        ensure_trunk_editable(await client.list_trunks(), trunk_id)
    except BridgeError as error:
        raise bridge_http_error(error) from None
    try:
        data = await client.save_trunk({"id": trunk_id, **body})
    except BridgeError as error:
        raise bridge_http_error(error) from None
    trunk = sanitize_trunk(data)
    if trunk["id"] != trunk_id:
        raise bridge_http_error()
    audit(session, principal, "asterisk_trunk.updated", trunk_id)
    session.commit()
    return trunk


def _applied_routes(value: object) -> list[dict[str, str]]:
    if not isinstance(value, dict):
        raise bridge_http_error()
    rows = value.get("applied_routes")
    if not isinstance(rows, list):
        raise bridge_http_error()
    result: list[dict[str, str]] = []
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("route_id"), str) or not isinstance(row.get("number"), str):
            raise bridge_http_error()
        result.append({"route_id": row["route_id"], "number": row["number"]})
    return result


@router.post("/asterisk/apply")
async def apply_asterisk(
    principal: Principal = Depends(require_principal),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    settings = require_operator_manager(principal)
    if registry.calls:
        raise HTTPException(status_code=409, detail="Apply is unavailable while calls are active")
    try:
        applied = _applied_routes(await bridge_client(settings).apply())
    except BridgeError as error:
        raise bridge_http_error(error) from None
    managed = session.scalars(
        select(PhoneNumber).where(PhoneNumber.organization_id == principal.organization_id)
    ).all()
    applied_keys = {(item["route_id"], item["number"]) for item in applied}
    missing_pending = [
        phone
        for phone in managed
        if phone.enabled
        and not phone.pbx_applied
        and (phone.id, phone.number) not in applied_keys
    ]
    for phone in managed:
        phone.pbx_applied = (phone.id, phone.number) in applied_keys
    if missing_pending:
        session.commit()
        raise HTTPException(
            status_code=502,
            detail="FreePBX apply readback did not match pending routes",
        )
    for item in applied:
        phone = session.scalar(
            select(PhoneNumber).where(
                PhoneNumber.organization_id == principal.organization_id,
                PhoneNumber.id == item["route_id"],
                PhoneNumber.number == item["number"],
            )
        )
        if phone:
            audit(session, principal, "phone_number.applied", phone.id)
    audit(session, principal, "asterisk.apply", None)
    session.commit()
    return {"applied_routes": applied}

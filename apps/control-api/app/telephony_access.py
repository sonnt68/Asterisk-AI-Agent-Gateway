"""Common authorization, payload, and redaction helpers for PBX routes."""

from typing import Any

from fastapi import HTTPException
from pydantic import SecretStr

from app.auth import Principal
from app.freepbx_client import BridgeError, FreePbxBridgeClient
from app.settings import Settings, get_settings


def is_operator_manager(principal: Principal, settings: Settings | None = None) -> bool:
    settings = settings or get_settings()
    return bool(
        principal.role in {"owner", "admin"}
        and settings.freepbx_operator_organization_id
        and principal.organization_id == settings.freepbx_operator_organization_id
    )


def require_operator_manager(principal: Principal) -> Settings:
    settings = get_settings()
    if not is_operator_manager(principal, settings):
        raise HTTPException(status_code=403, detail="PBX management is restricted")
    return settings


def bridge_client(settings: Settings | None = None) -> FreePbxBridgeClient:
    return FreePbxBridgeClient(settings or get_settings())


def bridge_http_error(error: BridgeError | None = None) -> HTTPException:
    if error and error.status_code == 409:
        return HTTPException(status_code=409, detail="FreePBX bridge rejected the change")
    if error and error.status_code == 422:
        return HTTPException(status_code=422, detail="FreePBX bridge rejected the input")
    return HTTPException(status_code=502, detail="FreePBX bridge request failed")


def bridge_unavailable_error() -> HTTPException:
    return HTTPException(status_code=503, detail="FreePBX bridge is unavailable")


def _safe_string(value: object, default: str = "") -> str:
    if not isinstance(value, str):
        return default
    if any(char in value for char in ("\x00", "\r", "\n")):
        return default
    return value


def _safe_id(value: object) -> str:
    if isinstance(value, int) and value > 0:
        return str(value)
    return _safe_string(value)


def sanitize_trunk(value: object) -> dict[str, object]:
    """Return the public trunk shape without accepting or returning passwords."""
    data = value.get("trunk", value) if isinstance(value, dict) else {}
    if not isinstance(data, dict):
        data = {}
    codecs = data.get("codecs", [])
    if not isinstance(codecs, list):
        codecs = []
    return {
        "id": _safe_id(data.get("id")),
        "name": _safe_string(data.get("name")),
        "host": _safe_string(data.get("host")),
        "port": data.get("port", 5060) if isinstance(data.get("port", 5060), int) else 5060,
        "transport": _safe_string(data.get("transport")),
        "authentication": _safe_string(data.get("authentication"), "none"),
        "registration": _safe_string(data.get("registration"), "none"),
        "username": _safe_string(data.get("username")),
        "auth_username": _safe_string(data.get("auth_username")),
        "match": _safe_string(data.get("match")),
        "from_domain": _safe_string(data.get("from_domain")),
        "from_user": _safe_string(data.get("from_user")),
        "contact_user": _safe_string(data.get("contact_user")),
        "outbound_caller_id": _safe_string(data.get("outbound_caller_id")),
        "codecs": [_safe_string(item) for item in codecs if isinstance(item, str)],
        "enabled": bool(data.get("enabled", True)),
        "password_set": bool(data.get("password_set", False)),
    }


def ensure_trunk_editable(value: object, trunk_id: str) -> None:
    """Reject edits that could overwrite a native mode outside our subset."""
    rows = value.get("trunks", value) if isinstance(value, dict) else value
    if not isinstance(rows, list):
        raise bridge_http_error()
    for row in rows:
        if not isinstance(row, dict) or _safe_id(row.get("id")) != trunk_id:
            continue
        authentication = row.get("authentication", "none")
        registration = row.get("registration", "none")
        if authentication not in {"none", "outbound"} or registration not in {"none", "send"}:
            raise HTTPException(
                status_code=422,
                detail="Trunk uses an unsupported native mode and is read-only",
            )
        return


def trunk_payload(model: Any, *, include_unset: bool = False) -> dict[str, object]:
    payload = model.model_dump(exclude_none=True, exclude_unset=include_unset)
    password = payload.get("password")
    if isinstance(password, SecretStr):
        payload["password"] = password.get_secret_value()
    return payload


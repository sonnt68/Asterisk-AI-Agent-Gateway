"""Partner-initiated outbound origination through scoped ARI."""

import re

import aiohttp
from gateway.control_policy import require_command_scope

from app.database import SessionLocal
from app.destination_policy import destination_allowed
from app.models import PartnerApp
from app.realtime_registry import Connection, registry
from app.settings import get_settings


async def originate(connection: Connection, message: dict[str, object]) -> None:
    request_id = str(message.get("request_id", ""))
    if request_id and request_id in connection.idempotency:
        await connection.send_json(connection.idempotency[request_id])
        return
    require_command_scope("outbound.originate", connection.scopes)
    payload = message.get("payload")
    if not isinstance(payload, dict):
        raise ValueError("Outbound payload must be an object")
    context = str(payload.get("context", ""))
    extension = str(payload.get("extension", ""))
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", context) or not re.fullmatch(
        r"[A-Za-z0-9*#+_-]{1,80}", extension
    ):
        raise PermissionError("Outbound destination syntax is not allowed")
    with SessionLocal() as session:
        app = session.get(PartnerApp, connection.partner_app_id)
        allowed = set(app.allowed_destinations.split(",")) if app else set()
    if not destination_allowed(context, extension, allowed):
        raise PermissionError("Outbound destination is not in the partner app allowlist")
    timeout = int(payload.get("timeout", 30))
    if timeout < 1 or timeout > 120:
        raise ValueError("Outbound timeout must be between 1 and 120 seconds")

    call = registry.reserve_call(connection)
    settings = get_settings()
    auth = aiohttp.BasicAuth(settings.ari_username or "", settings.ari_password or "")
    params = {
        # The /n suppresses Local channel optimisation. Without it Asterisk
        # collapses the Local channel once both legs are up, and the bridge
        # loses the media path to AudioSocket: the call connects, the partner
        # is told it started, and not one audio frame ever arrives.
        "endpoint": f"Local/{extension}@{context}/n",
        "app": "asterisk-ai-gateway",
        "appArgs": f"outbound,{call.id}",
        "timeout": str(timeout),
    }
    try:
        async with aiohttp.ClientSession(auth=auth) as session:
            async with session.post(f"{settings.ari_base_url}/channels", params=params) as response:
                if response.status >= 400:
                    raise RuntimeError(f"ARI originate returned {response.status}")
                channel = await response.json()
        call.channel_id = str(channel["id"])
        result = {"type": "outbound.accepted", "call_id": call.id}
        if request_id:
            result["request_id"] = request_id
            connection.remember(request_id, result)
        await connection.send_json(result)
    except Exception:
        registry.finish_call(call.id)
        raise

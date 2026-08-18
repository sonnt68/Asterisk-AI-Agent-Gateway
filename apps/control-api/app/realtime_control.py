"""Scope, tenant ownership, and destination policy for partner commands."""

import re

from gateway.control_policy import require_command_scope

from app.database import SessionLocal
from app.metrics import command_outcomes
from app.models import PartnerApp
from app.realtime_registry import Connection, registry


async def handle_control(connection: Connection, message: dict[str, object]) -> None:
    request_id = str(message.get("request_id", ""))
    if request_id and request_id in connection.idempotency:
        await connection.send_json(connection.idempotency[request_id])
        return
    command = str(message.get("command"))
    require_command_scope(command, connection.scopes)
    call_id = str(message.get("call_id"))
    if not registry.owns_call(call_id, connection):
        raise LookupError("No active gateway call owns this connection")
    call = registry.calls[call_id]
    payload = message.get("payload", {})
    if command.startswith(("transfer.", "route.")) and command != "transfer.cancel":
        validate_destination(connection, payload)
    if command == "audio.clear":
        await connection.send_json({"type": "audio.cleared", "call_id": call_id})
    else:
        from app.call_control import execute

        if not call.channel_id:
            raise LookupError("Call channel is not active yet")
        await execute(call.channel_id, command, payload, call_id=call.id)
    response = {"type": "call.control.accepted", "call_id": call_id}
    if request_id:
        response["request_id"] = request_id
        connection.remember(request_id, response)
    await connection.send_json(response)
    command_outcomes.labels("accepted").inc()


def validate_destination(connection: Connection, payload: object) -> None:
    if not isinstance(payload, dict):
        raise ValueError("Command payload must be an object")
    context = str(payload.get("context", ""))
    extension = str(payload.get("extension", ""))
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", context) or not re.fullmatch(
        r"[A-Za-z0-9*#+_-]{1,80}", extension
    ):
        raise PermissionError("Destination syntax is not allowed")
    with SessionLocal() as session:
        app = session.get(PartnerApp, connection.partner_app_id)
        allowed = set(app.allowed_destinations.split(",")) if app else set()
    if f"{context}:{extension}" not in allowed:
        raise PermissionError("Destination is not in the partner app allowlist")

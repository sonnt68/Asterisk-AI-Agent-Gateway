"""Authenticated partner WebSocket and protocol frame routing."""

import contextlib
import json
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.database import SessionLocal
from app.metrics import audio_bytes, command_outcomes, partner_disconnects
from app.models import ApiKey
from app.realtime_control import handle_control
from app.realtime_registry import Connection, registry
from app.security import timestamp_expired, verify_realtime_token
from app.settings import get_settings

router = APIRouter()


async def send_error(socket: WebSocket, code: str, message: str) -> None:
    await socket.send_json({"type": "error", "code": code, "message": message})


async def handle_binary(socket: WebSocket, connection: Connection | None, frame: bytes) -> None:
    if not connection:
        await send_error(socket, "protocol-invalid", "Register before sending audio")
        return
    if len(frame) <= 16:
        await send_error(socket, "audio-invalid", "Binary audio frame is too short")
        return
    call_id = str(UUID(bytes=frame[:16]))
    call = registry.calls.get(call_id)
    if not call or call.connection_id != connection.id:
        await send_error(socket, "call-not-active", "Audio call is not active")
        return
    if not await socket.app.state.call_lifecycle.send_to_asterisk(call, frame[16:]):
        await send_error(socket, "media-unavailable", "Asterisk media is unavailable")
    else:
        audio_bytes.labels("partner_to_asterisk").inc(len(frame) - 16)


async def handle_json(
    socket: WebSocket,
    connection: Connection | None,
    subject: dict[str, str],
    payload: dict[str, object],
) -> Connection | None:
    message_type = payload.get("type")
    if message_type == "session.register":
        if payload.get("protocol_version") != "1" or payload.get("agent_slug") != subject["agent_slug"]:
            await send_error(socket, "registration-rejected", "Agent slug or protocol version is invalid")
            return connection
        if connection or registry.find_agent(subject["agent_slug"]):
            await send_error(socket, "agent-in-use", "Agent slug already has an active connection")
            return connection
        connection = registry.register(subject, socket)
        presence = getattr(socket.app.state, "presence", None)
        if presence:
            try:
                registered = await presence.register(
                    connection.agent_slug, connection.id
                )
            except Exception:
                registry.remove(connection.id)
                await connection.close()
                await send_error(
                    socket, "presence-unavailable", "Connection lease store is unavailable"
                )
                await socket.close(code=1013)
                return None
            if not registered:
                registry.remove(connection.id)
                await connection.close()
                await send_error(
                    socket, "agent-in-use", "Agent slug is leased by another instance"
                )
                return None
        await connection.send_json({"type": "session.ready", "connection_id": connection.id})
    elif message_type == "heartbeat" and connection:
        presence = getattr(socket.app.state, "presence", None)
        if presence:
            try:
                lease_active = await presence.heartbeat(
                    connection.agent_slug, connection.id
                )
            except Exception:
                await send_error(
                    socket, "presence-unavailable", "Connection lease store is unavailable"
                )
                await socket.close(code=1013)
                return connection
            if not lease_active:
                await socket.close(code=1012)
                return connection
        await connection.send_json({"type": "heartbeat.ack"})
    elif message_type == "call.control" and connection:
        try:
            await handle_control(connection, payload)
        except (PermissionError, ValueError) as error:
            command_outcomes.labels("denied").inc()
            await send_error(socket, "command-denied", str(error))
        except (KeyError, LookupError, RuntimeError) as error:
            command_outcomes.labels("failed").inc()
            await send_error(socket, "command-failed", str(error))
    elif message_type == "outbound.originate" and connection:
        from app.outbound_calls import originate

        try:
            await originate(connection, payload)
        except (PermissionError, RuntimeError, ValueError) as error:
            await send_error(socket, "outbound-failed", str(error))
    elif message_type == "outbound.cancel" and connection:
        await cancel_outbound(socket, connection, payload)
    else:
        await send_error(socket, "protocol-invalid", "Register a supported protocol v1 session first")
    return connection


async def cancel_outbound(
    socket: WebSocket, connection: Connection, payload: dict[str, object]
) -> None:
    call_id = str(payload.get("call_id", ""))
    if not registry.owns_call(call_id, connection):
        await send_error(socket, "call-not-active", "Outbound call is not active")
        return
    call = registry.calls[call_id]
    if call.channel_id:
        from app.call_control import execute

        await execute(call.channel_id, "call.hangup", {})


@router.websocket("/v1/realtime")
async def realtime(socket: WebSocket) -> None:
    token = socket.query_params.get("token")
    subject = verify_realtime_token(token, get_settings()) if token else None
    if not subject or not token_key_is_active(subject):
        await socket.close(code=4401)
        return
    await socket.accept()
    connection: Connection | None = None
    try:
        while True:
            event = await socket.receive()
            if event.get("type") == "websocket.disconnect":
                raise WebSocketDisconnect
            if event.get("bytes") is not None:
                await handle_binary(socket, connection, event["bytes"])
            elif event.get("text"):
                connection = await handle_json(socket, connection, subject, json.loads(event["text"]))
    except (WebSocketDisconnect, ValueError):
        pass
    finally:
        if connection:
            await disconnect_partner(socket, connection)


def token_key_is_active(subject: dict[str, str]) -> bool:
    if not subject.get("api_key_id"):
        return True
    with SessionLocal() as session:
        key = session.get(ApiKey, subject["api_key_id"])
        return bool(key and not key.revoked_at and not timestamp_expired(key.expires_at))


async def disconnect_partner(socket: WebSocket, connection: Connection) -> None:
    partner_disconnects.inc()
    presence = getattr(socket.app.state, "presence", None)
    if presence:
        with contextlib.suppress(Exception):
            await presence.unregister(connection.agent_slug, connection.id)
    owned = registry.remove(connection.id)
    await connection.close()
    from app.call_control import execute

    for call in owned:
        if call.channel_id:
            with contextlib.suppress(Exception):
                await execute(call.channel_id, "call.hangup", {})

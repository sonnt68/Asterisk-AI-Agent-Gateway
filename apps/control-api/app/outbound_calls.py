"""Partner-initiated outbound origination through scoped ARI."""

import asyncio
import logging
import re
import time
from datetime import UTC, datetime
from uuid import uuid4

import aiohttp
from gateway.control_policy import require_command_scope

from app.call_signals import call_snapshot, publish_status
from app.database import SessionLocal
from app.destination_policy import destination_allowed
from app.outbound_number_policy import resolve_outbound_policy_async
from app.realtime_registry import Connection, registry
from app.settings import get_settings

logger = logging.getLogger(__name__)


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
    if "caller_number" in payload:
        policy = await resolve_outbound_policy_async(
            connection.organization_id,
            connection.partner_app_id,
            payload["caller_number"],
            session_factory=SessionLocal,
        )
    else:
        policy = await resolve_outbound_policy_async(
            connection.organization_id,
            connection.partner_app_id,
            session_factory=SessionLocal,
        )
    if not destination_allowed(context, extension, policy.allowed_destinations):
        raise PermissionError("Outbound destination is not in the partner app allowlist")
    timeout = int(payload.get("timeout", 30))
    if timeout < 1 or timeout > 120:
        raise ValueError("Outbound timeout must be between 1 and 120 seconds")

    # Both values have passed the syntax and partner allowlist checks above;
    # capture them before the durable start gate and any ARI side effects.
    call = registry.reserve_call(connection)
    call.called_number = extension
    call.routing_context = context
    # Bind identities before POST: a busy destination can be destroyed before
    # Asterisk's HTTP response reaches us. Both Local legs belong to this call.
    call.channel_id = str(uuid4())
    call.other_channel_id = str(uuid4())
    call.accepted = asyncio.Event()
    call.dial_deadline = time.monotonic() + timeout
    try:
        await registry.persist_start(call)
    except Exception:
        registry.finish_call(call.id)
        call.accepted.set()
        raise
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
        "channelId": call.channel_id,
        "otherChannelId": call.other_channel_id,
    }
    body = None
    if policy.caller_number is not None:
        params["callerId"] = policy.caller_number
        body = {"variables": {"__TRUNKCIDOVERRIDE": policy.caller_number}}
    try:
        async with aiohttp.ClientSession(auth=auth, timeout=aiohttp.ClientTimeout(total=10)) as session:
            request = {"params": params}
            if body is not None:
                request["json"] = body
            async with session.post(f"{settings.ari_base_url}/channels", **request) as response:
                if response.status >= 400:
                    raise RuntimeError(f"ARI originate returned {response.status}")
                await response.json()
        result = {"type": "outbound.accepted", "call_id": call.id}
        if request_id:
            result["request_id"] = request_id
            connection.remember(request_id, result)
        await connection.send_json(result)
        await publish_status(call, registry, "dialing")
    except Exception as error:
        registry.finish_call(call.id)
        call.accepted.set()
        store = getattr(registry, "history_store", None)
        if store is not None:
            call.status = "failed"
            call.reason = "originate_failed"
            call.ended_at = datetime.now(UTC)
            call.duration_seconds = max(
                0, int((call.ended_at - call.created_at).total_seconds())
            )
            call.sequence += 1
            call.updated_at = call.ended_at.isoformat()
            try:
                await store.record(call, call_snapshot(call))
            except Exception:
                logger.exception(
                    "failed to persist originate failure call_id=%s", call.id
                )
        # An HTTP/partner transport failure can happen after channel creation.
        async with aiohttp.ClientSession(auth=auth, timeout=aiohttp.ClientTimeout(total=5)) as session:
            for channel_id in (call.channel_id, call.other_channel_id):
                try:
                    async with session.delete(f"{settings.ari_base_url}/channels/{channel_id}"):
                        pass
                except Exception:
                    pass
        if isinstance(error, (aiohttp.ClientError, TimeoutError)):
            raise RuntimeError("Asterisk originate is unavailable") from None
        raise
    finally:
        call.accepted.set()

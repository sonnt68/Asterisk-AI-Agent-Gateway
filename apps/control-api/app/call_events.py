"""Dispatch correlated ARI evidence without confusing Local/media helper legs."""

import asyncio
import logging
from typing import TYPE_CHECKING

import aiohttp

from app.call_signals import DIAL_STATUSES, publish_status
from app.metrics import ari_events

if TYPE_CHECKING:
    from app.call_lifecycle import CallLifecycle
    from app.realtime_registry import ActiveCall

logger = logging.getLogger(__name__)


class CallEvents:
    def __init__(self, lifecycle: "CallLifecycle") -> None:
        self.lifecycle = lifecycle

    async def dispatch(
        self, event: dict[str, object], session: aiohttp.ClientSession, *, replay: bool = False
    ) -> None:
        lifecycle = self.lifecycle
        event_type = event.get("type")
        if not replay:
            ari_events.labels(str(event_type or "unknown")).inc()
        channel = event.get("peer") if event_type == "Dial" else event.get("channel")
        if not isinstance(channel, dict) or not isinstance(channel.get("id"), str):
            return
        channel_id = channel["id"]
        call = lifecycle.registry.by_channel(channel_id)
        if call and call.accepted is not None and not replay and (
            not call.accepted.is_set() or call.event_task is not None
        ):
            # ARI events can beat the HTTP originate response. Partners must
            # receive outbound.accepted and dialing before later transitions.
            # Queue per call rather than blocking the shared ARI listener on
            # one HTTP response. Replay preserves this call's event order.
            call.pending_events.append(event)
            if call.event_task is None:
                call.event_task = asyncio.create_task(self._replay_after_acceptance(call))
            return
        if event_type == "Dial":
            if call and channel_id == call.channel_id:
                status = str(event.get("dialstatus", ""))
                if call.answered and status != "ANSWER":
                    return
                if status in DIAL_STATUSES:
                    call.dial_status = status
                if status == "RINGING":
                    await publish_status(call, lifecycle.registry, "ringing")
                elif status == "ANSWER":
                    await publish_status(call, lifecycle.registry, "answered")
            return
        if event_type == "ChannelHangupRequest":
            if call and channel_id == call.channel_id and isinstance(event.get("cause"), int):
                call.hangup_cause = event["cause"]
            return
        if event_type == "ChannelDestroyed":
            if call:
                if channel_id in {call.channel_id, call.other_channel_id}:
                    cause = event.get("cause")
                    if isinstance(cause, int) and (cause or call.hangup_cause is None):
                        call.hangup_cause = cause
                if channel_id == call.channel_id:
                    await lifecycle.cleanup(call, session, notify=True)
                elif channel_id == call.media_channel_id:
                    await lifecycle.cleanup(call, session, notify=True, reason="media_failed")
            return
        if event_type == "StasisEnd":
            transfer_call = lifecycle.registry.by_transfer_channel(channel_id)
            if transfer_call:
                transfer_call.transfer_channel_id = None
                connection = lifecycle.registry.connections.get(transfer_call.connection_id)
                if connection:
                    await connection.send_json({"type": "transfer.ended", "call_id": transfer_call.id})
            elif call and channel_id == call.channel_id and call.end_task is None:
                call.in_stasis = False
                call.end_task = asyncio.create_task(self._finish_after_stasis(call))
            return
        if event_type == "ChannelStateChange":
            await lifecycle._on_channel_state_change(channel_id, channel, session)
            return
        if event_type != "StasisStart" or str(channel.get("name", "")).startswith("AudioSocket/"):
            return
        args = event.get("args")
        if isinstance(args, list) and args:
            if args[0] == "externalmedia":
                return
            if len(args) >= 2 and args[0] == "transfer-helper":
                await lifecycle._attach_transfer_helper(str(args[1]), channel_id, session)
                return
            if len(args) >= 2 and args[0] == "outbound":
                await lifecycle._start_outbound(str(args[1]), channel_id, channel, session)
                return
        await lifecycle._start_inbound(channel_id, channel, session)

    async def _replay_after_acceptance(self, call: "ActiveCall") -> None:
        try:
            await call.accepted.wait()
            if self.lifecycle.registry.calls.get(call.id) is not call:
                return
            # The listener can reconnect while HTTP originate is in flight.
            # Deferred work must not retain its now-closed ClientSession.
            async with self.lifecycle.ari.session() as session:
                try:
                    while call.pending_events and self.lifecycle.registry.calls.get(call.id) is call:
                        await self.dispatch(call.pending_events.popleft(), session, replay=True)
                except Exception:
                    logger.exception("Queued call event failed")
                    await self.lifecycle.cleanup(call, session, notify=True, reason="event_failed")
        except asyncio.CancelledError:
            raise
        finally:
            call.pending_events.clear()
            call.event_task = None

    async def _finish_after_stasis(self, call: "ActiveCall") -> None:
        # Let the serial listener consume ChannelDestroyed (and its cause)
        # first. A hand-back to dialplan may never produce that event.
        try:
            await asyncio.sleep(0.2)
            async with self.lifecycle.ari.session() as session:
                await self.lifecycle.cleanup(call, session, notify=True)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Deferred call cleanup failed")

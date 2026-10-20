"""Own ARI call events, bridges, partner events, and cleanup."""

import asyncio
import logging
import time
from urllib.parse import quote

import aiohttp
from gateway.external_media_manager import ExternalMediaManager

from app.ari_requests import AriRequests
from app.call_events import CallEvents
from app.call_media import CallMedia
from app.call_signals import publish_status, remember_completed, termination
from app.metrics import call_outcomes, call_setup_seconds
from app.realtime_registry import ActiveCall, Connection, ConnectionRegistry
from app.settings import Settings

logger = logging.getLogger(__name__)


class CallLifecycle:
    def __init__(
        self,
        settings: Settings,
        registry: ConnectionRegistry,
        audio_server: object,
        external_media: ExternalMediaManager,
    ) -> None:
        self.registry = registry
        self.ari = AriRequests(settings)
        self.media = CallMedia(settings, registry, audio_server, external_media, self.ari)

    async def on_ari_event(
        self, event: dict[str, object], session: aiohttp.ClientSession
    ) -> None:
        await CallEvents(self).dispatch(event, session)

    async def _on_channel_state_change(
        self,
        channel_id: str,
        channel: dict[str, object],
        session: aiohttp.ClientSession,
    ) -> None:
        """Activate an outbound call once the callee actually answers."""
        call = self.registry.by_channel(channel_id)
        if not call or call.channel_id != channel_id:
            return
        if channel.get("state") == "Ringing":
            await publish_status(call, self.registry, "ringing")
            return
        if channel.get("state") != "Up":
            return
        await publish_status(call, self.registry, "answered")
        if not call.in_stasis or call.bridge_id or call.activating:
            return
        connection = self.registry.connections.get(call.connection_id)
        if not connection:
            await self.ari.delete(session, f"/channels/{quote(channel_id, safe='')}")
            return
        # Claim the call before yielding, so a repeated answer event finds it taken.
        call.activating = True
        await self._activate_call(call, channel, connection, session)

    async def _start_outbound(
        self,
        call_id: str,
        channel_id: str,
        channel: dict[str, object],
        session: aiohttp.ClientSession,
    ) -> None:
        call = self.registry.calls.get(call_id)
        connection = self.registry.connections.get(call.connection_id) if call else None
        if not call or not connection:
            await self.ari.delete(session, f"/channels/{quote(channel_id, safe='')}")
            return
        if call.channel_id and call.channel_id != channel_id:
            return
        call.channel_id = channel_id
        call.in_stasis = True
        if call.activating or call.bridge_id:
            return
        if str(channel.get("state") or "") != "Up" and not call.answered:
            # A dialled channel enters Stasis while the far end is still
            # ringing. Activating here would answer our own leg and emit
            # call.started, so the partner would greet a phone nobody has
            # picked up and its audio would land nowhere. Wait for the
            # ChannelStateChange that says the callee answered.
            return
        await publish_status(call, self.registry, "answered")
        call.activating = True
        await self._activate_call(call, channel, connection, session)

    async def _attach_transfer_helper(
        self, call_id: str, channel_id: str, session: aiohttp.ClientSession
    ) -> None:
        call = self.registry.calls.get(call_id)
        if not call or not call.bridge_id:
            await self.ari.delete(session, f"/channels/{quote(channel_id, safe='')}")
            return
        call.transfer_channel_id = channel_id
        for attempt in range(25):
            try:
                await self.ari.post(
                    session,
                    f"/bridges/{quote(call.bridge_id, safe='')}/addChannel",
                    channel=channel_id,
                )
                connection = self.registry.connections.get(call.connection_id)
                if connection:
                    await connection.send_json(
                        {"type": "transfer.consulting", "call_id": call.id}
                    )
                return
            except RuntimeError:
                if attempt == 24:
                    raise
                await asyncio.sleep(0.1)

    async def _start_inbound(
        self,
        channel_id: str,
        channel: dict[str, object],
        session: aiohttp.ClientSession,
    ) -> None:
        agent_slug = await self.ari.channel_variable(
            session, channel_id, "AI_GATEWAY_AGENT"
        )
        connection = self.registry.find_agent(agent_slug or "")
        if not connection:
            await self.ari.delete(session, f"/channels/{quote(channel_id, safe='')}")
            return
        call = self.registry.create_call(channel_id, connection)
        try:
            await self.registry.persist_start(call)
        except Exception:
            logger.exception("inbound call history start failed call_id=%s", call.id)
            self.registry.finish_call(call.id)
            await self.ari.delete(session, f"/channels/{quote(channel_id, safe='')}")
            return
        call.in_stasis = True
        call.activating = True
        await self._activate_call(call, channel, connection, session)

    async def _activate_call(
        self,
        call: ActiveCall,
        channel: dict[str, object],
        connection: Connection,
        session: aiohttp.ClientSession,
    ) -> None:
        started_at = time.monotonic()
        if not call.channel_id:
            raise RuntimeError("Call channel is unavailable")
        try:
            await self.ari.post(
                session, f"/channels/{quote(call.channel_id, safe='')}/answer"
            )
            await publish_status(call, self.registry, "answered")
            bridge = await self.ari.post(session, "/bridges", type="mixing")
            call.bridge_id = str(bridge["id"])
            await self.ari.post(
                session,
                f"/bridges/{quote(call.bridge_id, safe='')}/addChannel",
                channel=call.channel_id,
            )
            await self.media.create_and_attach(call, session)
            caller = channel.get("caller") if isinstance(channel.get("caller"), dict) else {}
            await connection.send_json(
                {
                    "type": "call.started",
                    "call_id": call.id,
                    "sequence": 1,
                    "agent_slug": call.agent_slug,
                    "media": self.media.wire_format(),
                    "caller": caller,
                }
            )
            call_setup_seconds.observe(time.monotonic() - started_at)
            call_outcomes.labels("started").inc()
        except Exception:
            call_outcomes.labels("failed").inc()
            await self.cleanup(call, session, notify=True, reason="media_failed")
            raise

    async def send_to_asterisk(self, call: ActiveCall, payload: bytes) -> bool:
        return await self.media.send_to_asterisk(call, payload)

    async def on_media_uuid(self, connection_id: str, call_id: str) -> bool:
        return await self.media.bind(connection_id, call_id)

    async def on_media_audio(self, connection_id: str, payload: bytes) -> None:
        await self.media.on_audio(connection_id, payload)

    async def on_media_dtmf(self, connection_id: str, digit: str) -> None:
        await self.media.on_dtmf(connection_id, digit)

    async def on_media_disconnect(self, connection_id: str) -> None:
        await self.media.disconnect(connection_id)

    async def cleanup(
        self, call: ActiveCall, session: aiohttp.ClientSession, notify: bool,
        reason: str | None = None,
    ) -> None:
        if not self.registry.finish_call(call.id):
            return
        if call.end_task and call.end_task is not asyncio.current_task():
            call.end_task.cancel()
        status, call.reason = termination(call)
        if reason:
            status, call.reason = "failed", reason
        try:
            await publish_status(call, self.registry, status)
        except Exception:
            pass
        snapshot = remember_completed(call, self.registry)
        await self.media.close(call)
        for channel_id in (
            call.transfer_channel_id,
            call.media_channel_id,
            call.channel_id,
            call.other_channel_id,
        ):
            if channel_id:
                try:
                    await self.ari.delete(
                        session, f"/channels/{quote(channel_id, safe='')}"
                    )
                except Exception:
                    pass
        if call.bridge_id:
            try:
                await self.ari.delete(
                    session, f"/bridges/{quote(call.bridge_id, safe='')}"
                )
            except Exception:
                pass
        connection = self.registry.connections.get(call.connection_id)
        if notify and connection:
            try:
                await connection.send_json({**snapshot, "type": "call.ended"})
            except Exception:
                pass
        call_outcomes.labels("ended").inc()

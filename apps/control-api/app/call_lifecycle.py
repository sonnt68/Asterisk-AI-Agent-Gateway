"""Own ARI call events, bridges, partner events, and cleanup."""

import asyncio
import time
from urllib.parse import quote

import aiohttp
from gateway.external_media_manager import ExternalMediaManager

from app.ari_requests import AriRequests
from app.call_media import CallMedia
from app.metrics import ari_events, call_outcomes, call_setup_seconds
from app.realtime_registry import ActiveCall, Connection, ConnectionRegistry
from app.settings import Settings


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
        event_type = event.get("type")
        ari_events.labels(str(event_type or "unknown")).inc()
        channel = event.get("channel")
        if not isinstance(channel, dict) or not isinstance(channel.get("id"), str):
            return
        channel_id = channel["id"]
        if event_type == "StasisEnd":
            await self._on_stasis_end(channel_id, session)
            return
        if event_type == "ChannelStateChange":
            await self._on_channel_state_change(channel_id, channel, session)
            return
        if event_type == "ChannelDestroyed":
            # A dialled channel that never answered produces no StasisEnd, so
            # without this the reservation would sit in the registry forever
            # and active_calls would drift away from reality.
            call = self.registry.by_channel(channel_id)
            if call:
                await self.cleanup(call, session, notify=True)
            return
        if event_type != "StasisStart" or str(channel.get("name", "")).startswith(
            "AudioSocket/"
        ):
            return
        args = event.get("args")
        if isinstance(args, list) and args and args[0] == "externalmedia":
            return
        if isinstance(args, list) and len(args) >= 2 and args[0] == "transfer-helper":
            await self._attach_transfer_helper(str(args[1]), channel_id, session)
            return
        if isinstance(args, list) and len(args) >= 2 and args[0] == "outbound":
            await self._start_outbound(str(args[1]), channel_id, channel, session)
            return
        await self._start_inbound(channel_id, channel, session)

    async def _on_stasis_end(
        self, channel_id: str, session: aiohttp.ClientSession
    ) -> None:
        transfer_call = self.registry.by_transfer_channel(channel_id)
        if transfer_call:
            transfer_call.transfer_channel_id = None
            connection = self.registry.connections.get(transfer_call.connection_id)
            if connection:
                await connection.send_json(
                    {"type": "transfer.ended", "call_id": transfer_call.id}
                )
            return
        call = self.registry.by_channel(channel_id)
        if call:
            await self.cleanup(call, session, notify=True)

    async def _on_channel_state_change(
        self,
        channel_id: str,
        channel: dict[str, object],
        session: aiohttp.ClientSession,
    ) -> None:
        """Activate an outbound call once the callee actually answers."""
        if str(channel.get("state") or "") != "Up":
            return
        call = self.registry.by_channel(channel_id)
        if not call or call.bridge_id or call.activating or call.channel_id != channel_id:
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
        call.channel_id = channel_id
        if call.activating or call.bridge_id:
            return
        if str(channel.get("state") or "") != "Up":
            # A dialled channel enters Stasis while the far end is still
            # ringing. Activating here would answer our own leg and emit
            # call.started, so the partner would greet a phone nobody has
            # picked up and its audio would land nowhere. Wait for the
            # ChannelStateChange that says the callee answered.
            return
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
            await self.cleanup(call, session, notify=False)
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
        self, call: ActiveCall, session: aiohttp.ClientSession, notify: bool
    ) -> None:
        if not self.registry.finish_call(call.id):
            return
        await self.media.close(call)
        for channel_id in (
            call.transfer_channel_id,
            call.media_channel_id,
            call.channel_id,
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
                await connection.send_json({"type": "call.ended", "call_id": call.id})
            except Exception:
                pass
        call_outcomes.labels("ended").inc()

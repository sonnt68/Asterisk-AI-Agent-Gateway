"""Create, bridge, stream, and release a call's media channel."""

import asyncio
import contextlib
from urllib.parse import quote

import aiohttp
from gateway.audiosocket import channel_format
from gateway.external_media_manager import ExternalMediaManager

from app.ari_requests import AriRequests
from app.metrics import audio_bytes, audiosocket_connections
from app.realtime_registry import ActiveCall, ConnectionRegistry
from app.settings import Settings


class CallMedia:
    def __init__(
        self,
        settings: Settings,
        registry: ConnectionRegistry,
        audio_server: object,
        external_media: ExternalMediaManager,
        ari: AriRequests,
    ) -> None:
        self.settings = settings
        self.registry = registry
        self.audio_server = audio_server
        self.external_media = external_media
        self.ari = ari

    async def create_and_attach(
        self, call: ActiveCall, session: aiohttp.ClientSession
    ) -> None:
        if self.settings.media_transport == "externalmedia":
            media = await self._create_external_media(call, session)
        else:
            media = await self._create_audiosocket(call, session)
        call.media_channel_id = str(media["id"])
        for attempt in range(25):
            try:
                await self.ari.post(
                    session,
                    f"/bridges/{quote(call.bridge_id or '', safe='')}/addChannel",
                    channel=call.media_channel_id,
                )
                break
            except RuntimeError:
                if attempt == 24:
                    raise
                await asyncio.sleep(0.1)
        if call.media_transport == "externalmedia":
            await self.ari.post(
                session,
                f"/bridges/{quote(call.bridge_id or '', safe='')}/play",
                media="sound:silence/1",
            )

    async def _create_external_media(
        self, call: ActiveCall, session: aiohttp.ClientSession
    ) -> dict[str, object]:
        call.media_transport = "externalmedia"
        port = await self.external_media.allocate(
            call.id, lambda payload: self.on_external_audio(call.id, payload)
        )
        return await self.ari.post(
            session,
            "/channels/externalMedia",
            app="asterisk-ai-gateway",
            data=f"externalmedia,{call.id}",
            external_host=f"{self.settings.external_media_advertise_host}:{port}",
            format="ulaw",
            encapsulation="rtp",
            transport="udp",
            connection_type="client",
            direction="both",
        )

    def wire_format(self) -> dict[str, object]:
        """The media format the partner will actually receive and must send.

        The two transports differ, so the partner cannot assume one: external
        media is negotiated as µ-law at the trunk's own 8 kHz, while
        AudioSocket carries signed linear at the configured rate.
        """
        if self.settings.media_transport == "externalmedia":
            return {"encoding": "pcm_mulaw", "sample_rate": 8000, "channels": 1}
        return {
            "encoding": "pcm_s16le",
            "sample_rate": self.settings.media_sample_rate,
            "channels": 1,
        }

    async def _create_audiosocket(
        self, call: ActiveCall, session: aiohttp.ClientSession
    ) -> dict[str, object]:
        # The `c(...)` format is what Asterisk plays the frames at; the type
        # byte does not carry the rate on this version. It must therefore
        # match the rate advertised to the partner exactly.
        endpoint = (
            f"AudioSocket/{self.settings.audiosocket_advertise_host}:"
            f"{self.settings.audiosocket_port}/{call.id}/"
            f"c({channel_format(self.settings.media_sample_rate)})"
        )
        return await self.ari.post(
            session,
            "/channels",
            endpoint=endpoint,
            app="asterisk-ai-gateway",
            timeout="30",
            json_body={"channelVars": {"AUDIOSOCKET_UUID": call.id}},
        )

    async def on_external_audio(self, call_id: str, payload: bytes) -> None:
        await self._send_to_partner(self.registry.calls.get(call_id), payload)

    async def on_audio(self, connection_id: str, payload: bytes) -> None:
        await self._send_to_partner(
            self.registry.by_media_connection(connection_id), payload
        )

    async def _send_to_partner(
        self, call: ActiveCall | None, payload: bytes
    ) -> None:
        connection = self.registry.connections.get(call.connection_id) if call else None
        if call and connection:
            audio_bytes.labels("asterisk_to_partner").inc(len(payload))
            await connection.send_audio(call.id, payload)

    async def send_to_asterisk(self, call: ActiveCall, payload: bytes) -> bool:
        if call.media_transport == "externalmedia":
            return self.external_media.send_audio(call.id, payload)
        if not call.media_connection_id:
            return False
        return await self.audio_server.send_audio(call.media_connection_id, payload)

    async def bind(self, connection_id: str, call_id: str) -> bool:
        bound = self.registry.bind_media(connection_id, call_id) is not None
        if bound:
            audiosocket_connections.inc()
        return bound

    async def on_dtmf(self, connection_id: str, digit: str) -> None:
        call = self.registry.by_media_connection(connection_id)
        connection = self.registry.connections.get(call.connection_id) if call else None
        if call and connection:
            await connection.send_json(
                {"type": "dtmf.received", "call_id": call.id, "digit": digit}
            )

    async def disconnect(self, connection_id: str) -> None:
        call = self.registry.by_media_connection(connection_id)
        if call:
            call.media_connection_id = None
            audiosocket_connections.dec()

    async def close(self, call: ActiveCall) -> None:
        if call.media_connection_id:
            audiosocket_connections.dec()
            with contextlib.suppress(Exception):
                await self.audio_server.disconnect(call.media_connection_id)
        self.external_media.close(call.id)

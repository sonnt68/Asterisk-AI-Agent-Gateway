"""Bounded asynchronous server for Asterisk's AudioSocket protocol."""

import asyncio
import contextlib
import logging
import socket
from collections.abc import Awaitable, Callable
from uuid import uuid4

from gateway.audiosocket import (
    AUDIO_TYPE_RATES,
    GATEWAY_AUDIO_TYPE,
    GATEWAY_SAMPLE_RATE,
    MAX_PAYLOAD_BYTES,
    TYPE_DTMF,
    TYPE_ERROR,
    TYPE_TERMINATE,
    AudioSocketFrame,
    AudioSocketHandshake,
    encode_frame,
)

LOGGER = logging.getLogger("gateway.audiosocket")


class AudioSocketServer:
    def __init__(
        self,
        host: str,
        port: int,
        on_uuid: Callable[[str, str], Awaitable[bool]],
        on_audio: Callable[[str, bytes], Awaitable[None]],
        on_disconnect: Callable[[str], Awaitable[None]],
        on_dtmf: Callable[[str, str], Awaitable[None]],
    ) -> None:
        self.host = host
        self.port = port
        self.on_uuid = on_uuid
        self.on_audio = on_audio
        self.on_disconnect = on_disconnect
        self.on_dtmf = on_dtmf
        self.server: asyncio.Server | None = None
        self.writers: dict[str, asyncio.StreamWriter] = {}
        self.connection_uuids: dict[str, str] = {}
        # One rate-mismatch warning per connection; a per-frame log would drown
        # the call it is describing.
        self._rate_warned: set[str] = set()

    async def start(self) -> None:
        if self.server:
            return
        self.server = await asyncio.start_server(self._handle, self.host, self.port)

    async def stop(self) -> None:
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            self.server = None
        writers = list(self.writers.values())
        self.writers.clear()
        self.connection_uuids.clear()
        for writer in writers:
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()

    async def send_audio(self, connection_id: str, payload: bytes) -> bool:
        writer = self.writers.get(connection_id)
        if not writer:
            return False
        if len(payload) > MAX_PAYLOAD_BYTES:
            # A partner pacing its own playback can hand over more than one
            # frame's worth at a time. Dropping it lost audio silently and
            # pushed partners toward 8 kHz just to stay under the limit, so
            # split instead.
            for start in range(0, len(payload), MAX_PAYLOAD_BYTES):
                chunk = payload[start : start + MAX_PAYLOAD_BYTES]
                if not await self.send_audio(connection_id, chunk):
                    return False
            return True
        try:
            # The type declares the rate to Asterisk; 0x10 would play this
            # 16 kHz audio at 8 kHz.
            writer.write(encode_frame(GATEWAY_AUDIO_TYPE, payload))
            await writer.drain()
            return True
        except (ConnectionError, RuntimeError):
            return False

    async def disconnect(self, connection_id: str) -> None:
        writer = self.writers.pop(connection_id, None)
        if writer:
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()

    async def _handle(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        connection_id = str(uuid4())
        transport_socket = writer.get_extra_info("socket")
        if transport_socket:
            with contextlib.suppress(OSError):
                transport_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.writers[connection_id] = writer
        handshake = AudioSocketHandshake()
        try:
            while True:
                header = await reader.readexactly(3)
                length = int.from_bytes(header[1:], "big")
                if length > MAX_PAYLOAD_BYTES:
                    raise ValueError("AudioSocket payload exceeds gateway frame limit")
                frame = AudioSocketFrame(header[0], await reader.readexactly(length))
                if handshake.call_uuid is None:
                    call_uuid = handshake.accept(frame)
                    if not call_uuid or not await self.on_uuid(connection_id, call_uuid):
                        writer.write(encode_frame(TYPE_ERROR, b"uuid-rejected"))
                        await writer.drain()
                        return
                    self.connection_uuids[connection_id] = call_uuid
                    continue
                handshake.accept(frame)
                if frame.kind in AUDIO_TYPE_RATES and frame.payload:
                    inbound_rate = AUDIO_TYPE_RATES[frame.kind]
                    if inbound_rate != GATEWAY_SAMPLE_RATE:
                        # Asterisk is sending a rate the partner contract does
                        # not carry. Say so once rather than silently handing
                        # the partner audio at the wrong speed.
                        if connection_id not in self._rate_warned:
                            self._rate_warned.add(connection_id)
                            LOGGER.warning(
                                "Asterisk sends %d Hz but the gateway carries %d Hz",
                                inbound_rate,
                                GATEWAY_SAMPLE_RATE,
                            )
                    await self.on_audio(connection_id, frame.payload)
                elif frame.kind == TYPE_DTMF and frame.payload:
                    await self.on_dtmf(
                        connection_id, frame.payload.decode("ascii", errors="ignore")[:1]
                    )
                elif frame.kind in {TYPE_TERMINATE, TYPE_ERROR}:
                    return
        except (asyncio.IncompleteReadError, ConnectionError, ValueError):
            pass
        finally:
            self.writers.pop(connection_id, None)
            self.connection_uuids.pop(connection_id, None)
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()
            await self.on_disconnect(connection_id)

"""Bounded asynchronous server for Asterisk's AudioSocket protocol."""

import asyncio
import contextlib
import socket
from collections.abc import Awaitable, Callable
from uuid import uuid4

from gateway.audiosocket import (
    MAX_PAYLOAD_BYTES,
    TYPE_AUDIO,
    TYPE_DTMF,
    TYPE_ERROR,
    TYPE_TERMINATE,
    AudioSocketFrame,
    AudioSocketHandshake,
    encode_frame,
)


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
        if not writer or len(payload) > MAX_PAYLOAD_BYTES:
            return False
        try:
            writer.write(encode_frame(TYPE_AUDIO, payload))
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
                if frame.kind == TYPE_AUDIO and frame.payload:
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

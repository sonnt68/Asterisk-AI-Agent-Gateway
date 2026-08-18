"""In-process WebSocket handles and gateway call ownership."""

import asyncio
from dataclasses import dataclass, field
from uuid import UUID, uuid4

from fastapi import WebSocket

from app.metrics import (
    active_calls,
    active_connections,
    partner_audio_drops,
    partner_audio_queue_depth,
)


@dataclass(slots=True)
class Connection:
    id: str
    organization_id: str
    partner_app_id: str
    agent_slug: str
    scopes: set[str]
    socket: WebSocket
    send_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    audio_queue: asyncio.Queue[bytes] = field(
        default_factory=lambda: asyncio.Queue(maxsize=100)
    )
    audio_sender: asyncio.Task[None] | None = None
    idempotency: dict[str, dict[str, object]] = field(default_factory=dict)

    async def send_json(self, payload: dict[str, object]) -> None:
        async with self.send_lock:
            await self.socket.send_json(payload)

    async def send_audio(self, call_id: str, payload: bytes) -> None:
        frame = UUID(call_id).bytes + payload
        if self.audio_queue.full():
            self.audio_queue.get_nowait()
            partner_audio_drops.inc()
        self.audio_queue.put_nowait(frame)
        partner_audio_queue_depth.set(self.audio_queue.qsize())

    def start(self) -> None:
        self.audio_sender = asyncio.create_task(self._send_audio_loop())

    async def close(self) -> None:
        if self.audio_sender:
            self.audio_sender.cancel()
            try:
                await self.audio_sender
            except asyncio.CancelledError:
                pass
            self.audio_sender = None
        partner_audio_queue_depth.set(0)

    def remember(self, request_id: str, response: dict[str, object]) -> None:
        if len(self.idempotency) >= 256:
            self.idempotency.pop(next(iter(self.idempotency)))
        self.idempotency[request_id] = response

    async def _send_audio_loop(self) -> None:
        while True:
            frame = await self.audio_queue.get()
            async with self.send_lock:
                await self.socket.send_bytes(frame)
            partner_audio_queue_depth.set(self.audio_queue.qsize())


@dataclass(slots=True)
class ActiveCall:
    id: str
    channel_id: str | None
    connection_id: str
    agent_slug: str
    bridge_id: str | None = None
    media_channel_id: str | None = None
    media_connection_id: str | None = None
    transfer_channel_id: str | None = None
    media_transport: str = "audiosocket"
    # Playback ids this call started, so a partner can only stop its own.
    playbacks: set[str] = field(default_factory=set)


class ConnectionRegistry:
    def __init__(self) -> None:
        self.connections: dict[str, Connection] = {}
        self.calls: dict[str, ActiveCall] = {}

    def register(self, payload: dict[str, str], socket: WebSocket) -> Connection:
        connection = Connection(
            id=str(uuid4()),
            organization_id=payload["organization_id"],
            partner_app_id=payload["partner_app_id"],
            agent_slug=payload["agent_slug"],
            scopes=set(payload["scopes"].split(",")),
            socket=socket,
        )
        self.connections[connection.id] = connection
        connection.start()
        active_connections.set(len(self.connections))
        return connection

    def remove(self, connection_id: str) -> list[ActiveCall]:
        self.connections.pop(connection_id, None)
        active_connections.set(len(self.connections))
        return [call for call in self.calls.values() if call.connection_id == connection_id]

    def find_agent(self, agent_slug: str) -> Connection | None:
        return next((item for item in self.connections.values() if item.agent_slug == agent_slug), None)

    def create_call(self, channel_id: str, connection: Connection) -> ActiveCall:
        call = ActiveCall(str(uuid4()), channel_id, connection.id, connection.agent_slug)
        self.calls[call.id] = call
        active_calls.set(len(self.calls))
        return call

    def reserve_call(self, connection: Connection) -> ActiveCall:
        call = ActiveCall(str(uuid4()), None, connection.id, connection.agent_slug)
        self.calls[call.id] = call
        active_calls.set(len(self.calls))
        return call

    def by_channel(self, channel_id: str) -> ActiveCall | None:
        return next(
            (call for call in self.calls.values() if channel_id in {call.channel_id, call.media_channel_id}),
            None,
        )

    def by_media_connection(self, connection_id: str) -> ActiveCall | None:
        return next(
            (call for call in self.calls.values() if call.media_connection_id == connection_id),
            None,
        )

    def by_transfer_channel(self, channel_id: str) -> ActiveCall | None:
        return next(
            (call for call in self.calls.values() if call.transfer_channel_id == channel_id),
            None,
        )

    def bind_media(self, connection_id: str, call_id: str) -> ActiveCall | None:
        call = self.calls.get(call_id)
        if call:
            call.media_connection_id = connection_id
        return call

    def owns_call(self, call_id: str, connection: Connection) -> bool:
        call = self.calls.get(call_id)
        return bool(call and call.connection_id == connection.id)

    def finish_call(self, call_id: str) -> ActiveCall | None:
        call = self.calls.pop(call_id, None)
        active_calls.set(len(self.calls))
        return call


registry = ConnectionRegistry()

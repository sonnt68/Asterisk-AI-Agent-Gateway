"""Small async SDK hiding token exchange and binary call framing."""

import asyncio
import contextlib
import json
from collections.abc import AsyncIterator
from urllib.parse import quote, urlparse, urlunparse
from uuid import UUID

import httpx
from websockets.asyncio.client import ClientConnection, connect


class GatewayClient:
    def __init__(self, gateway_url: str, api_key: str, agent_slug: str) -> None:
        self.gateway_url = gateway_url.rstrip("/")
        self.api_key = api_key
        self.agent_slug = agent_slug
        self.socket: ClientConnection | None = None
        self._heartbeat: asyncio.Task[None] | None = None

    async def connect(self) -> None:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                f"{self.gateway_url}/api/v1/realtime/tokens",
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
            response.raise_for_status()
            token = response.json()["token"]
        parsed = urlparse(self.gateway_url)
        ws_scheme = "wss" if parsed.scheme == "https" else "ws"
        ws_url = urlunparse((ws_scheme, parsed.netloc, "/v1/realtime", "", f"token={quote(token)}", ""))
        self.socket = await connect(ws_url, max_size=2**20)
        await self.socket.send(
            json.dumps(
                {
                    "type": "session.register",
                    "agent_slug": self.agent_slug,
                    "protocol_version": "1",
                }
            )
        )
        ready = json.loads(await self.socket.recv())
        if ready.get("type") != "session.ready":
            raise ConnectionError(f"Gateway registration failed: {ready}")
        self._heartbeat = asyncio.create_task(self._heartbeat_loop())

    async def close(self) -> None:
        if self._heartbeat:
            self._heartbeat.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._heartbeat
        if self.socket:
            await self.socket.close()
            self.socket = None

    async def messages(self) -> AsyncIterator[dict[str, object]]:
        if not self.socket:
            raise ConnectionError("Gateway client is not connected")
        async for message in self.socket:
            if isinstance(message, bytes):
                if len(message) <= 16:
                    continue
                yield {
                    "type": "audio",
                    "call_id": str(UUID(bytes=message[:16])),
                    "audio": message[16:],
                }
            else:
                yield json.loads(message)

    async def send_audio(self, call_id: str, pcm16: bytes) -> None:
        if not self.socket:
            raise ConnectionError("Gateway client is not connected")
        await self.socket.send(UUID(call_id).bytes + pcm16)

    async def control(
        self, call_id: str, command: str, payload: dict[str, object] | None = None
    ) -> None:
        if not self.socket:
            raise ConnectionError("Gateway client is not connected")
        await self.socket.send(
            json.dumps(
                {
                    "type": "call.control",
                    "call_id": call_id,
                    "command": command,
                    "payload": payload or {},
                }
            )
        )

    async def originate(self, context: str, extension: str, timeout: int = 30) -> None:
        if not self.socket:
            raise ConnectionError("Gateway client is not connected")
        await self.socket.send(
            json.dumps(
                {
                    "type": "outbound.originate",
                    "payload": {
                        "context": context,
                        "extension": extension,
                        "timeout": timeout,
                    },
                }
            )
        )

    async def cancel_outbound(self, call_id: str) -> None:
        if not self.socket:
            raise ConnectionError("Gateway client is not connected")
        await self.socket.send(json.dumps({"type": "outbound.cancel", "call_id": call_id}))

    async def _heartbeat_loop(self) -> None:
        while self.socket:
            await asyncio.sleep(10)
            await self.socket.send(json.dumps({"type": "heartbeat"}))

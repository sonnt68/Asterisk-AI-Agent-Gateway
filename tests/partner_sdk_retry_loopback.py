"""Small real HTTP/WebSocket server used by SDK auth retry tests."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Sequence

from aiohttp import WSMsgType, web


class LoopbackGateway:
    """Script token and WebSocket outcomes without touching the gateway app."""

    def __init__(
        self,
        token_statuses: Sequence[int],
        ws_actions: Sequence[int | str],
        *,
        block_token: bool = False,
        block_handshake: bool = False,
    ) -> None:
        self.token_statuses = list(token_statuses)
        self.ws_actions = list(ws_actions)
        self.block_token = block_token
        self.block_handshake = block_handshake
        self.handshake_started = asyncio.Event()
        self.release_handshake = asyncio.Event()
        self.token_started = asyncio.Event()
        self.release_token = asyncio.Event()
        self.hold = asyncio.Event()
        self.token_requests = 0
        self.ws_requests = 0
        self.registered = 0
        self.token_headers: list[str] = []
        self.tokens: list[str] = []
        self.ws_tokens: list[str] = []
        self.token_times: list[float] = []
        self._sockets: list[web.WebSocketResponse] = []
        self._runner: web.AppRunner | None = None
        self.url = ""

    async def start(self) -> None:
        app = web.Application()
        app.router.add_post("/api/v1/realtime/tokens", self._token)
        app.router.add_get("/v1/realtime", self._socket)
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, "127.0.0.1", 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]  # type: ignore[union-attr]
        self.url = f"http://127.0.0.1:{port}"

    async def stop(self) -> None:
        self.release_token.set()
        self.release_handshake.set()
        self.hold.set()
        for socket in self._sockets:
            if not socket.closed:
                await socket.close()
        if self._runner is not None:
            await self._runner.cleanup()

    async def _token(self, request: web.Request) -> web.Response:
        self.token_requests += 1
        self.token_times.append(time.monotonic())
        self.token_headers.append(request.headers.get("Authorization", ""))
        self.token_started.set()
        if self.block_token:
            await self.release_token.wait()
        status = self.token_statuses.pop(0) if self.token_statuses else 200
        if status != 200:
            return web.Response(status=status)
        token = f"rt-token-{self.token_requests}"
        self.tokens.append(token)
        return web.json_response({"token": token})

    async def _socket(self, request: web.Request) -> web.StreamResponse:
        self.ws_requests += 1
        self.handshake_started.set()
        if self.block_handshake:
            await self.release_handshake.wait()
        token = request.query.get("token", "")
        self.ws_tokens.append(token)
        action = self.ws_actions.pop(0) if self.ws_actions else "ready"
        if isinstance(action, int):
            return web.Response(status=action)

        socket = web.WebSocketResponse()
        await socket.prepare(request)
        self._sockets.append(socket)
        if action == "4401":
            await socket.close(code=4401)
            return socket

        message = await socket.receive()
        if message.type in {WSMsgType.CLOSE, WSMsgType.CLOSED, WSMsgType.ERROR}:
            return socket
        if message.type is WSMsgType.TEXT:
            registration = json.loads(message.data)
            if registration.get("type") == "session.register":
                self.registered += 1
                if action in {"ready", "ready-close"}:
                    await socket.send_json(
                        {"type": "session.ready", "connection_id": f"conn-{self.registered}"}
                    )
        if action in {"ready-close", "no-ready"}:
            await socket.close(code=1000)
        else:
            await self.hold.wait()
        return socket

"""Realtime protocol v1 client: token exchange, session, audio, and control."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

import aiohttp

from .errors import AuthenticationError, GatewayError, RateLimitedError
from .frames import decode_audio_frame, encode_audio_frame

LOGGER = logging.getLogger("asterisk_ai_gateway")

PROTOCOL_VERSION = "1"
DEFAULT_HEARTBEAT_SECONDS = 10.0
TOKEN_PATH = "/api/v1/realtime/tokens"
REALTIME_PATH = "/v1/realtime"

#: Close code the gateway uses for a dead token or a revoked key.
CLOSE_UNAUTHORIZED = 4401

EventHandler = Callable[[dict[str, Any]], Awaitable[None]]
AudioHandler = Callable[[str, bytes], Awaitable[None]]


@dataclass(slots=True)
class Audio:
    """One decoded binary frame: PCM s16le, 16 kHz, mono."""

    call_id: str
    pcm: bytes


class GatewayClient:
    """One partner connection to one ``agent_slug``.

    The gateway allows a single live connection per slug, so run exactly one
    client per slug. The client exchanges the API key for a five-minute
    realtime token, registers the session, heartbeats, reconnects with a
    fresh token, and hides the 16-byte audio envelope.
    """

    def __init__(
        self,
        gateway_url: str,
        api_key: str,
        agent_slug: str,
        *,
        heartbeat_interval: float = DEFAULT_HEARTBEAT_SECONDS,
        reconnect: bool = True,
        max_backoff: float = 30.0,
    ) -> None:
        self.gateway_url = gateway_url.rstrip("/")
        self.agent_slug = agent_slug
        self.heartbeat_interval = heartbeat_interval
        self.reconnect = reconnect
        self.max_backoff = max_backoff

        self._api_key = api_key
        self._socket: aiohttp.ClientWebSocketResponse | None = None
        self._send_lock = asyncio.Lock()
        self._connection_id: str | None = None
        self._closing = False

    def __repr__(self) -> str:  # pragma: no cover - diagnostics only
        return (
            f"GatewayClient(gateway_url={self.gateway_url!r}, "
            f"agent_slug={self.agent_slug!r}, api_key='***')"
        )

    @property
    def connection_id(self) -> str | None:
        """Gateway-assigned id of the current session, once registered."""
        return self._connection_id

    # ---------------------------------------------------------------- token

    async def realtime_token(self, session: aiohttp.ClientSession | None = None) -> str:
        """Exchange the long-lived API key for a five-minute realtime token."""
        owned = session is None
        session = session or aiohttp.ClientSession()
        try:
            headers = {"Authorization": f"Bearer {self._api_key}"}
            async with session.post(f"{self.gateway_url}{TOKEN_PATH}", headers=headers) as response:
                if response.status in (401, 403):
                    raise AuthenticationError(
                        f"Gateway refused the API key with HTTP {response.status}. "
                        "The key is invalid, revoked, expired, or its partner app is disabled."
                    )
                if response.status == 429:
                    raise RateLimitedError(
                        "Token exchange is rate limited. Reuse the live token instead of re-minting."
                    )
                if response.status >= 400:
                    raise GatewayError(f"Token exchange failed with HTTP {response.status}")
                return (await response.json())["token"]
        finally:
            if owned:
                await session.close()

    # ----------------------------------------------------------- connection

    async def stream(self) -> AsyncIterator[dict[str, Any] | Audio]:
        """Yield every JSON event and decoded :class:`Audio` frame.

        Reconnects with a fresh token on transport failures. An
        :class:`AuthenticationError` ends the stream: no amount of retrying
        revives a revoked key.
        """
        backoff = 1.0
        self._closing = False
        while not self._closing:
            try:
                async with aiohttp.ClientSession() as session:
                    token = await self.realtime_token(session)
                    url = self._websocket_url(token)
                    async with session.ws_connect(url) as socket:
                        self._socket = socket
                        await self._register()
                        heartbeat = asyncio.create_task(self._heartbeat_loop())
                        backoff = 1.0
                        try:
                            async for message in socket:
                                item = self._decode(message)
                                if item is not None:
                                    yield item
                        finally:
                            heartbeat.cancel()
                            with contextlib.suppress(asyncio.CancelledError):
                                await heartbeat
                        if socket.close_code == CLOSE_UNAUTHORIZED:
                            raise AuthenticationError(
                                "Gateway closed the session with 4401: the token expired "
                                "or the API key was revoked."
                            )
            except (AuthenticationError, asyncio.CancelledError):
                raise
            except (aiohttp.ClientError, GatewayError, OSError) as error:
                if self._closing or not self.reconnect:
                    raise
                LOGGER.warning("Gateway connection lost (%s); reconnecting in %.0fs", error, backoff)
            finally:
                self._socket = None
                self._connection_id = None

            if self._closing or not self.reconnect:
                return
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, self.max_backoff)

    async def run(
        self,
        on_event: EventHandler | None = None,
        on_audio: AudioHandler | None = None,
    ) -> None:
        """Consume :meth:`stream` and dispatch to handlers until closed."""
        async for item in self.stream():
            if isinstance(item, Audio):
                if on_audio is not None:
                    await on_audio(item.call_id, item.pcm)
            elif on_event is not None:
                await on_event(item)

    async def close(self) -> None:
        """Stop reconnecting and close the socket.

        The gateway hangs up every call this connection owns, so drain
        in-flight calls before calling this.
        """
        self._closing = True
        socket, self._socket = self._socket, None
        if socket is not None and not socket.closed:
            await socket.close()

    # -------------------------------------------------------------- sending

    async def send_audio(self, call_id: str | UUID, pcm: bytes) -> None:
        """Send PCM s16le 16 kHz mono audio to a call the connection owns."""
        await self._send_bytes(encode_audio_frame(call_id, pcm))

    async def control(
        self,
        call_id: str,
        command: str,
        payload: dict[str, Any] | None = None,
        *,
        request_id: str | None = None,
    ) -> str:
        """Send a scoped control command; returns the ``request_id`` used.

        The gateway remembers accepted results per connection, so replaying
        the same ``request_id`` never runs the ARI action twice.
        """
        request_id = request_id or str(uuid4())
        message: dict[str, Any] = {
            "type": "call.control",
            "request_id": request_id,
            "call_id": call_id,
            "command": command,
        }
        if payload:
            message["payload"] = payload
        await self._send_json(message)
        return request_id

    async def hangup(self, call_id: str, **kwargs: Any) -> str:
        """End the call. Requires ``calls:hangup``."""
        return await self.control(call_id, "call.hangup", **kwargs)

    async def hold(self, call_id: str, **kwargs: Any) -> str:
        """Place the caller on hold. Requires ``calls:hold``."""
        return await self.control(call_id, "call.hold", **kwargs)

    async def resume(self, call_id: str, **kwargs: Any) -> str:
        """Take the caller off hold. Requires ``calls:hold``."""
        return await self.control(call_id, "call.resume", **kwargs)

    async def mute(self, call_id: str, **kwargs: Any) -> str:
        """Mute the channel in both directions. Requires ``calls:mute``."""
        return await self.control(call_id, "call.mute", **kwargs)

    async def unmute(self, call_id: str, **kwargs: Any) -> str:
        """Unmute the channel. Requires ``calls:mute``."""
        return await self.control(call_id, "call.unmute", **kwargs)

    async def send_dtmf(self, call_id: str, digits: str, **kwargs: Any) -> str:
        """Play DTMF digits into the call. Requires ``calls:dtmf``."""
        return await self.control(call_id, "dtmf.send", {"digits": digits}, **kwargs)

    async def clear_audio(self, call_id: str, **kwargs: Any) -> str:
        """Drop buffered playback audio. Requires ``media:control``."""
        return await self.control(call_id, "audio.clear", **kwargs)

    async def transfer_blind(self, call_id: str, context: str, extension: str, **kwargs: Any) -> str:
        """Redirect the call. Destination must be allowlisted; ``calls:transfer``."""
        return await self.control(
            call_id, "transfer.blind", {"context": context, "extension": extension}, **kwargs
        )

    async def transfer_attended(
        self, call_id: str, context: str, extension: str, **kwargs: Any
    ) -> str:
        """Start a consulting transfer. Destination must be allowlisted; ``calls:transfer``."""
        return await self.control(
            call_id, "transfer.attended", {"context": context, "extension": extension}, **kwargs
        )

    async def transfer_cancel(self, call_id: str, **kwargs: Any) -> str:
        """Abandon a consulting transfer. Requires ``calls:transfer``."""
        return await self.control(call_id, "transfer.cancel", **kwargs)

    async def route(self, call_id: str, target: str, context: str, extension: str, **kwargs: Any) -> str:
        """Route to ``queue``, ``ring_group`` or ``voicemail``. Requires ``calls:route``."""
        if target not in {"queue", "ring_group", "voicemail"}:
            raise ValueError("Route target must be queue, ring_group or voicemail")
        return await self.control(
            call_id, f"route.{target}", {"context": context, "extension": extension}, **kwargs
        )

    async def originate(
        self,
        context: str,
        extension: str,
        *,
        timeout: int = 30,
        request_id: str | None = None,
    ) -> str:
        """Place an outbound call. Requires ``calls:originate``.

        Returns the ``request_id``. The call is live only once ``call.started``
        arrives; ``outbound.accepted`` merely means Asterisk took the request.
        """
        if not 1 <= timeout <= 120:
            raise ValueError("Outbound timeout must be between 1 and 120 seconds")
        request_id = request_id or str(uuid4())
        await self._send_json(
            {
                "type": "outbound.originate",
                "request_id": request_id,
                "payload": {"context": context, "extension": extension, "timeout": timeout},
            }
        )
        return request_id

    async def cancel_outbound(self, call_id: str) -> None:
        """Hang up an outbound call this connection started."""
        await self._send_json({"type": "outbound.cancel", "call_id": call_id})

    # ------------------------------------------------------------ internals

    def _websocket_url(self, token: str) -> str:
        base = self.gateway_url
        if base.startswith("https://"):
            base = "wss://" + base[len("https://") :]
        elif base.startswith("http://"):
            base = "ws://" + base[len("http://") :]
        return f"{base}{REALTIME_PATH}?token={token}"

    async def _register(self) -> None:
        await self._send_json(
            {
                "type": "session.register",
                "agent_slug": self.agent_slug,
                "protocol_version": PROTOCOL_VERSION,
            }
        )

    async def _heartbeat_loop(self) -> None:
        while True:
            await asyncio.sleep(self.heartbeat_interval)
            try:
                await self._send_json({"type": "heartbeat"})
            except GatewayError:
                return

    def _decode(self, message: aiohttp.WSMessage) -> dict[str, Any] | Audio | None:
        if message.type is aiohttp.WSMsgType.BINARY:
            call_id, pcm = decode_audio_frame(message.data)
            return Audio(call_id=call_id, pcm=pcm)
        if message.type is aiohttp.WSMsgType.TEXT:
            event = message.json()
            if event.get("type") == "session.ready":
                self._connection_id = event.get("connection_id")
            return event
        return None

    async def _send_json(self, message: dict[str, Any]) -> None:
        socket = self._require_socket()
        async with self._send_lock:
            await socket.send_json(message)

    async def _send_bytes(self, frame: bytes) -> None:
        socket = self._require_socket()
        async with self._send_lock:
            await socket.send_bytes(frame)

    def _require_socket(self) -> aiohttp.ClientWebSocketResponse:
        socket = self._socket
        if socket is None or socket.closed:
            raise GatewayError("Realtime session is not connected")
        return socket

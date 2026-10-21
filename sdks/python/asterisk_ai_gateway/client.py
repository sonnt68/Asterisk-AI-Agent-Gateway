"""Realtime protocol v1 client: token exchange, session, audio, and control."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import re
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Any, TypedDict
from urllib.parse import quote, urlencode
from uuid import UUID, uuid4

import aiohttp
from yarl import URL

from .errors import (
    AuthenticationError,
    GatewayError,
    GatewayHTTPError,
    RateLimitedError,
    SessionSupersededError,
)
from .frames import decode_audio_frame, encode_audio_frame

LOGGER = logging.getLogger("asterisk_ai_gateway")

PROTOCOL_VERSION = "1"
DEFAULT_HEARTBEAT_SECONDS = 10.0
TOKEN_PATH = "/api/v1/realtime/tokens"
REALTIME_PATH = "/v1/realtime"
PARTNER_CALLS_PATH = "/api/v1/partner/calls"

#: Close code the gateway uses for a dead token or a revoked key.
CLOSE_UNAUTHORIZED = 4401
#: Close code for a session replaced by a newer registration of its slug.
CLOSE_SUPERSEDED = 4409
AUTH_RETRY_LIMIT = 3

EventHandler = Callable[[dict[str, Any]], Awaitable[None]]
AudioHandler = Callable[[str, bytes], Awaitable[None]]


class CallRecord(TypedDict, total=False):
    """A customer-visible durable call summary returned by the Gateway."""

    call_id: str
    partner_app_id: str | None
    agent_slug: str | None
    direction: str
    source: str
    status: str
    terminal: bool
    answered: bool
    reason: str | None
    hangup_cause: int | None
    dial_status: str | None
    sequence: int
    created_at: str
    updated_at: str
    answered_at: str | None
    ended_at: str | None
    duration_seconds: float | None
    talk_seconds: float | None
    history_complete: bool


class CallSignal(TypedDict, total=False):
    """One current call-status snapshot from the durable signal history."""

    type: str
    call_id: str
    status: str
    terminal: bool
    answered: bool
    reason: str | None
    hangup_cause: int | None
    dial_status: str | None
    sequence: int
    updated_at: str


class CallListResponse(TypedDict):
    items: list[CallRecord]
    next_cursor: str | None
    page: int | None
    page_size: int | None
    total: int | None
    total_pages: int | None


class CallSignalListResponse(TypedDict):
    items: list[CallSignal]
    next_cursor: str | None


def _query_params(**values: object) -> dict[str, str]:
    """Drop unset filters while preserving URL-safe string conversion."""
    return {key: str(value) for key, value in values.items() if value is not None}


def _call_history_path(call_id: str) -> str:
    """Encode a call id as one path segment and reject empty identifiers."""
    if not isinstance(call_id, str) or not call_id.strip():
        raise ValueError("call_id must be a non-empty string")
    return f"{PARTNER_CALLS_PATH}/{quote(call_id, safe='')}"


@dataclass(slots=True)
class Audio:
    """One decoded binary frame: mono PCM s16le at the call's announced rate."""

    call_id: str
    pcm: bytes


class GatewayClient:
    """One partner connection to one ``agent_slug``.

    The gateway keeps one live connection per slug: a newer registration
    replaces this one, which then raises :class:`SessionSupersededError`. The client exchanges the API key for a five-minute
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
        self._closed_event = asyncio.Event()

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

    # ----------------------------------------------------------- call history

    async def list_calls(
        self,
        *,
        limit: int = 50,
        cursor: str | None = None,
        status: str | None = None,
        direction: str | None = None,
        agent_slug: str | None = None,
        page: int | None = None,
        started_after: str | None = None,
        started_before: str | None = None,
    ) -> CallListResponse:
        """List this API key's durable calls using its ``calls:read`` scope.

        This is a direct API-key request and does not create a realtime token or
        open a WebSocket. The Gateway remains the authority for filter bounds,
        including the maximum page size of 100 and agent slug length of 80.
        ``page`` selects numbered pagination (1 through 2147483647); the
        Gateway rejects combining it with ``cursor`` using HTTP 422.
        """
        params = _query_params(
            limit=limit,
            cursor=cursor,
            status=status,
            direction=direction,
            agent_slug=agent_slug,
            page=page,
            started_after=started_after,
            started_before=started_before,
        )
        return await self._history_get(PARTNER_CALLS_PATH, params)

    async def get_call(self, call_id: str) -> CallRecord:
        """Return one customer-owned durable call summary."""
        path = _call_history_path(call_id)
        return await self._history_get(path, {})

    async def list_call_signals(
        self,
        call_id: str,
        *,
        limit: int = 50,
        cursor: str | None = None,
    ) -> CallSignalListResponse:
        """List status snapshots for one customer-owned call."""
        params = _query_params(limit=limit, cursor=cursor)
        return await self._history_get(f"{_call_history_path(call_id)}/signals", params)

    async def _history_get(self, path: str, params: dict[str, str]) -> Any:
        """Make one safe, non-retrying API-key request for call history."""
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Accept": "application/json",
        }
        query = urlencode(params)
        url = f"{self.gateway_url}{path}{f'?{query}' if query else ''}"
        async with aiohttp.ClientSession() as session:
            async with session.get(URL(url, encoded=True), headers=headers) as response:
                if not 200 <= response.status < 300:
                    raise GatewayHTTPError(response.status, method="GET", path=path)
                return await response.json()

    # ----------------------------------------------------------- connection

    async def stream(self) -> AsyncIterator[dict[str, Any] | Audio]:
        """Yield every JSON event and decoded :class:`Audio` frame.

        Reconnects with a fresh token on transport failures. Authentication
        failures allow three retries before raising :class:`AuthenticationError`.
        Successful registration resets the retry budget. A session replaced by a
        newer registration raises :class:`SessionSupersededError` and never
        reconnects.
        """
        backoff = 1.0
        auth_retries = 0
        self._closing = False
        self._closed_event.clear()
        while not self._closing:
            try:
                async with aiohttp.ClientSession() as session:
                    token = await self.realtime_token(session)
                    if self._closing:
                        return
                    url = self._websocket_url(token)
                    async with session.ws_connect(url) as socket:
                        if self._closing:
                            return
                        self._socket = socket
                        await self._register()
                        heartbeat = asyncio.create_task(self._heartbeat_loop())
                        try:
                            async for message in socket:
                                item = self._decode(message)
                                if isinstance(item, dict) and item.get("type") == "session.ready":
                                    auth_retries = 0
                                    backoff = 1.0
                                if item is not None:
                                    yield item
                        finally:
                            heartbeat.cancel()
                            with contextlib.suppress(asyncio.CancelledError):
                                await heartbeat
                        if socket.close_code == CLOSE_SUPERSEDED:
                            raise SessionSupersededError(
                                "Gateway closed the session with 4409: a newer connection "
                                "registered this agent slug."
                            )
                        if socket.close_code == CLOSE_UNAUTHORIZED:
                            raise AuthenticationError(
                                "Gateway closed the session with 4401: the token expired "
                                "or the API key was revoked."
                            )
            except (asyncio.CancelledError, SessionSupersededError):
                raise
            except (aiohttp.ClientError, GatewayError, OSError) as error:
                if self._closing:
                    return
                # Handshake exceptions include the token-bearing URL. Keep only
                # the HTTP status in diagnostics, including the terminal error.
                if isinstance(error, aiohttp.WSServerHandshakeError):
                    error_type = AuthenticationError if error.status in (401, 403) else GatewayError
                    error = error_type(f"WebSocket handshake failed with HTTP {error.status}")
                elif self._socket is not None and self._socket.close_code == CLOSE_UNAUTHORIZED:
                    error = AuthenticationError("Gateway refused the WebSocket session with 4401")
                if not self.reconnect:
                    raise error from None
                if isinstance(error, AuthenticationError):
                    if auth_retries >= AUTH_RETRY_LIMIT:
                        raise error from None
                    auth_retries += 1
                    LOGGER.warning(
                        "Gateway authentication failed; retry %d/%d in %.3fs",
                        auth_retries, AUTH_RETRY_LIMIT, min(backoff, self.max_backoff),
                    )
                else:
                    LOGGER.warning("Gateway connection lost (%s); reconnecting in %.3fs",
                                   error, min(backoff, self.max_backoff))
            finally:
                self._socket = None
                self._connection_id = None

            if self._closing or not self.reconnect:
                return
            try:
                await asyncio.wait_for(self._closed_event.wait(), timeout=min(backoff, self.max_backoff))
            except asyncio.TimeoutError:  # noqa: UP041 -- distinct from TimeoutError on Python 3.10
                pass
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
        self._closed_event.set()
        socket, self._socket = self._socket, None
        if socket is not None and not socket.closed:
            await socket.close()

    # -------------------------------------------------------------- sending

    async def send_audio(self, call_id: str | UUID, pcm: bytes) -> None:
        """Send mono PCM s16le to a call the connection owns.

        Use the rate `call.started` announced for this call, not a fixed one.
        """
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

    async def start_playback(self, call_id: str, media: str, **kwargs: Any) -> str:
        """Play an Asterisk media file into the call. Requires ``media:playback``.

        ``media`` must be ``sound:<name>`` or ``recording:<name>``; the gateway
        refuses every other scheme. The accepted response carries the
        ``playback_id`` needed to stop it.
        """
        return await self.control(call_id, "playback.start", {"media": media}, **kwargs)

    async def stop_playback(self, call_id: str, playback_id: str, **kwargs: Any) -> str:
        """Stop a playback this call started. Requires ``media:playback``."""
        return await self.control(
            call_id, "playback.stop", {"playback_id": playback_id}, **kwargs
        )

    async def set_variable(self, call_id: str, variable: str, value: object, **kwargs: Any) -> str:
        """Set a channel variable. Requires ``channel:variables``.

        Names live in the partner namespace and must match ``AI_[A-Z0-9_]``;
        dialplan functions such as ``CHANNEL(...)`` are refused.
        """
        return await self.control(
            call_id, "channel.set_var", {"variable": variable, "value": value}, **kwargs
        )

    async def continue_in_dialplan(
        self, call_id: str, context: str, extension: str, **kwargs: Any
    ) -> str:
        """Hand the call back to the dialplan. Requires ``calls:dialplan``.

        The destination must be allowlisted on the partner app, exactly as for
        a transfer.
        """
        return await self.control(
            call_id, "dialplan.continue", {"context": context, "extension": extension}, **kwargs
        )

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
        caller_number: str | None = None,
    ) -> str:
        """Place an outbound call. Requires ``calls:originate``.

        Returns the ``request_id``. The call is live only once ``call.started``
        arrives; ``outbound.accepted`` merely means Asterisk took the request.
        """
        if not 1 <= timeout <= 120:
            raise ValueError("Outbound timeout must be between 1 and 120 seconds")
        if caller_number is not None and (
            not isinstance(caller_number, str) or not re.fullmatch(r"\+?[0-9]{1,32}", caller_number)
        ):
            raise ValueError("Caller number must be an exact number with optional + and 1 to 32 digits")
        payload: dict[str, object] = {"context": context, "extension": extension, "timeout": timeout}
        if caller_number is not None:
            payload["caller_number"] = caller_number
        request_id = request_id or str(uuid4())
        await self._send_json(
            {
                "type": "outbound.originate",
                "request_id": request_id,
                "payload": payload,
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

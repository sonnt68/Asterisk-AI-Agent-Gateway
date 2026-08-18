"""Allocate isolated UDP listeners for Asterisk ExternalMedia calls."""

import asyncio
from collections.abc import Awaitable, Callable

from gateway.external_media_rtp import ExternalMediaProtocol


class ExternalMediaManager:
    def __init__(self, host: str) -> None:
        self.host = host
        self.sessions: dict[str, ExternalMediaProtocol] = {}

    async def allocate(
        self, call_id: str, on_pcm: Callable[[bytes], Awaitable[None]]
    ) -> int:
        loop = asyncio.get_running_loop()
        transport, protocol = await loop.create_datagram_endpoint(
            lambda: ExternalMediaProtocol(on_pcm), local_addr=(self.host, 0)
        )
        self.sessions[call_id] = protocol
        return int(transport.get_extra_info("sockname")[1])

    def send_audio(self, call_id: str, payload: bytes) -> bool:
        session = self.sessions.get(call_id)
        return bool(session and session.send_pcm(payload))

    def close(self, call_id: str) -> None:
        session = self.sessions.pop(call_id, None)
        if session:
            session.close()

    def close_all(self) -> None:
        for call_id in list(self.sessions):
            self.close(call_id)

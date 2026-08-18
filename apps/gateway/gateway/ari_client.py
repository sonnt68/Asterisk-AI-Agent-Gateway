"""Minimal gateway-owned Asterisk REST Interface client."""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from urllib.parse import quote

import aiohttp


@dataclass(frozen=True, slots=True)
class AriConfig:
    base_url: str
    username: str
    password: str
    app_name: str = "asterisk-ai-gateway"


class AriClient:
    def __init__(self, config: AriConfig) -> None:
        self.config = config
        self._session: aiohttp.ClientSession | None = None
        self.ready = False

    async def connect(self) -> None:
        self._session = aiohttp.ClientSession(
            auth=aiohttp.BasicAuth(self.config.username, self.config.password)
        )
        async with self._session.get(f"{self.config.base_url}/asterisk/info") as response:
            if response.status != 200:
                raise ConnectionError(f"ARI info request returned {response.status}")
        self.ready = True

    async def close(self) -> None:
        self.ready = False
        if self._session:
            await self._session.close()
            self._session = None

    async def command(self, method: str, path: str, **params: str) -> dict[str, object]:
        if not self._session or not self.ready:
            raise ConnectionError("ARI is not ready")
        async with self._session.request(
            method, f"{self.config.base_url}{path}", params=params
        ) as response:
            if response.status >= 400:
                raise RuntimeError(f"ARI {method} {path} returned {response.status}")
            return await response.json() if response.content_type == "application/json" else {}

    async def answer(self, channel_id: str) -> None:
        await self.command("POST", f"/channels/{quote(channel_id, safe='')}/answer")

    async def hangup(self, channel_id: str) -> None:
        await self.command("DELETE", f"/channels/{quote(channel_id, safe='')}")

    async def send_dtmf(self, channel_id: str, digits: str) -> None:
        await self.command("POST", f"/channels/{quote(channel_id, safe='')}/dtmf", dtmf=digits)

    async def hold(self, channel_id: str, enabled: bool) -> None:
        await self.command(
            "POST" if enabled else "DELETE", f"/channels/{quote(channel_id, safe='')}/hold"
        )

    async def mute(self, channel_id: str, enabled: bool) -> None:
        await self.command(
            "POST" if enabled else "DELETE",
            f"/channels/{quote(channel_id, safe='')}/mute",
            direction="both",
        )

    async def redirect(
        self, channel_id: str, context: str, extension: str, priority: str = "1"
    ) -> None:
        await self.command(
            "POST",
            f"/channels/{quote(channel_id, safe='')}/redirect",
            context=context,
            extension=extension,
            priority=priority,
        )

    async def originate(self, endpoint: str, app_args: str) -> dict[str, object]:
        return await self.command(
            "POST", "/channels", endpoint=endpoint, app=self.config.app_name, appArgs=app_args
        )


class AriSupervisor:
    def __init__(self, client: AriClient, retry_seconds: float = 2.0) -> None:
        self.client = client
        self.retry_seconds = retry_seconds
        self._running = False

    async def run(self, on_ready: Callable[[], Awaitable[None]]) -> None:
        if self._running:
            return
        self._running = True
        while self._running:
            try:
                await self.client.connect()
                await on_ready()
                return
            except Exception:
                await self.client.close()
                await asyncio.sleep(self.retry_seconds)

    async def stop(self) -> None:
        self._running = False
        await self.client.close()

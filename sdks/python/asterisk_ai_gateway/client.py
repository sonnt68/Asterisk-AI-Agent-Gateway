"""Small async client that hides API-key token exchange."""

from collections.abc import Awaitable, Callable

import aiohttp


class GatewayClient:
    def __init__(self, gateway_url: str, api_key: str, agent_slug: str) -> None:
        self.gateway_url = gateway_url.rstrip("/")
        self.api_key = api_key
        self.agent_slug = agent_slug

    async def realtime_token(self) -> str:
        async with aiohttp.ClientSession() as session:
            headers = {"Authorization": f"Bearer {self.api_key}"}
            async with session.post(f"{self.gateway_url}/api/v1/realtime/tokens", headers=headers) as response:
                response.raise_for_status()
                return (await response.json())["token"]

    async def connect(self, on_event: Callable[[dict[str, object]], Awaitable[None]]) -> None:
        token = await self.realtime_token()
        websocket_url = self.gateway_url.replace("https://", "wss://").replace("http://", "ws://")
        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(f"{websocket_url}/v1/realtime?token={token}") as socket:
                await socket.send_json({"type": "session.register", "agent_slug": self.agent_slug, "protocol_version": "1"})
                async for message in socket:
                    if message.type is aiohttp.WSMsgType.TEXT:
                        await on_event(message.json())

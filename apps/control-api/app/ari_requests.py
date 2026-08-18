"""Small checked wrappers around the ARI HTTP API."""

from urllib.parse import quote

import aiohttp

from app.settings import Settings


class AriRequests:
    def __init__(self, settings: Settings) -> None:
        self.base_url = settings.ari_base_url

    async def channel_variable(
        self, session: aiohttp.ClientSession, channel_id: str, variable: str
    ) -> str | None:
        path = f"/channels/{quote(channel_id, safe='')}/variable"
        async with session.get(
            f"{self.base_url}{path}", params={"variable": variable}
        ) as response:
            data = await response.json() if response.status == 200 else {}
        return data.get("value") if isinstance(data, dict) else None

    async def post(
        self,
        session: aiohttp.ClientSession,
        path: str,
        json_body: dict[str, object] | None = None,
        **params: str,
    ) -> dict[str, object]:
        async with session.post(
            f"{self.base_url}{path}", params=params, json=json_body
        ) as response:
            if response.status >= 400:
                raise RuntimeError(f"ARI POST {path} returned {response.status}")
            if response.content_type == "application/json":
                return await response.json()
            return {}

    async def delete(self, session: aiohttp.ClientSession, path: str) -> None:
        async with session.delete(f"{self.base_url}{path}") as response:
            if response.status not in {204, 404}:
                raise RuntimeError(f"ARI DELETE {path} returned {response.status}")

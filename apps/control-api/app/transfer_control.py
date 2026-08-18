"""Attended-transfer consult leg lifecycle."""

from urllib.parse import quote

import aiohttp

from app.realtime_registry import registry
from app.settings import get_settings


async def start(call_id: str, context: str, extension: str) -> None:
    call = registry.calls.get(call_id)
    if not call or not call.bridge_id:
        raise RuntimeError("Call bridge is unavailable")
    if call.transfer_channel_id:
        raise RuntimeError("An attended transfer is already active")
    settings = get_settings()
    auth = aiohttp.BasicAuth(settings.ari_username or "", settings.ari_password or "")
    params = {
        "endpoint": f"Local/{extension}@{context}",
        "app": "asterisk-ai-gateway",
        "appArgs": f"transfer-helper,{call.id}",
        "timeout": "30",
    }
    async with aiohttp.ClientSession(auth=auth) as session:
        async with session.post(f"{settings.ari_base_url}/channels", params=params) as response:
            if response.status >= 400:
                raise RuntimeError(f"ARI attended transfer returned {response.status}")
            channel = await response.json()
    call.transfer_channel_id = str(channel["id"])


async def cancel(call_id: str) -> None:
    call = registry.calls.get(call_id)
    if not call or not call.transfer_channel_id:
        raise RuntimeError("No attended transfer is active")
    settings = get_settings()
    auth = aiohttp.BasicAuth(settings.ari_username or "", settings.ari_password or "")
    channel_id = call.transfer_channel_id
    call.transfer_channel_id = None
    async with aiohttp.ClientSession(auth=auth) as session:
        async with session.delete(
            f"{settings.ari_base_url}/channels/{quote(channel_id, safe='')}"
        ) as response:
            if response.status not in {204, 404}:
                raise RuntimeError(f"ARI transfer cancel returned {response.status}")

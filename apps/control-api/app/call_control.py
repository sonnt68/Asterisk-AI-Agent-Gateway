"""Execute scoped partner controls against a gateway-owned ARI channel."""

from urllib.parse import quote

import aiohttp

from app.settings import get_settings


async def execute(
    channel_id: str,
    command: str,
    payload: dict[str, object],
    call_id: str | None = None,
) -> None:
    settings = get_settings()
    auth = aiohttp.BasicAuth(settings.ari_username or "", settings.ari_password or "")
    path = f"{settings.ari_base_url}/channels/{quote(channel_id, safe='')}"
    method = "POST"
    params: dict[str, str] = {}
    if command == "call.hangup":
        method = "DELETE"
    elif command == "dtmf.send":
        path += "/dtmf"
        params["dtmf"] = str(payload["digits"])
    elif command in {"call.hold", "call.resume"}:
        path += "/hold"
        method = "POST" if command == "call.hold" else "DELETE"
    elif command in {"call.mute", "call.unmute"}:
        path += "/mute"
        method = "POST" if command == "call.mute" else "DELETE"
        params["direction"] = "both"
    elif command == "transfer.attended":
        if not call_id:
            raise ValueError("Gateway call ID is required for attended transfer")
        from app.transfer_control import start

        await start(call_id, str(payload["context"]), str(payload["extension"]))
        return
    elif command == "transfer.cancel":
        if not call_id:
            raise ValueError("Gateway call ID is required to cancel transfer")
        from app.transfer_control import cancel

        await cancel(call_id)
        return
    elif command == "transfer.blind" or command.startswith("route."):
        path += "/redirect"
        params = {
            "context": str(payload["context"]),
            "extension": str(payload["extension"]),
            "priority": "1",
        }
    else:
        raise ValueError("Command has no ARI implementation")
    async with aiohttp.ClientSession(auth=auth) as session:
        async with session.request(method, path, params=params) as response:
            if response.status >= 400:
                raise RuntimeError(f"ARI rejected command with HTTP {response.status}")

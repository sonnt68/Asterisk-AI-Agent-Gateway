"""Execute scoped partner controls against a gateway-owned ARI channel."""

from urllib.parse import quote
from uuid import uuid4

import aiohttp

from app.settings import get_settings


async def execute(
    channel_id: str,
    command: str,
    payload: dict[str, object],
    call_id: str | None = None,
) -> dict[str, str] | None:
    """Run one scoped command against a gateway-owned channel.

    Returns a result the partner needs to act on later (a playback id), or
    None when the command has nothing to hand back.
    """
    settings = get_settings()
    auth = aiohttp.BasicAuth(settings.ari_username or "", settings.ari_password or "")
    path = f"{settings.ari_base_url}/channels/{quote(channel_id, safe='')}"
    method = "POST"
    params: dict[str, str] = {}
    result: dict[str, str] | None = None
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
    elif command == "playback.start":
        # The gateway mints the playback id so a partner can only ever stop a
        # playback the gateway attributed to its own call.
        playback_id = str(uuid4())
        path += f"/play/{quote(playback_id, safe='')}"
        params["media"] = str(payload["media"])
        result = {"playback_id": playback_id}
    elif command == "playback.stop":
        path = f"{settings.ari_base_url}/playbacks/{quote(str(payload['playback_id']), safe='')}"
        method = "DELETE"
    elif command == "channel.set_var":
        path += "/variable"
        params["variable"] = str(payload["variable"])
        params["value"] = str(payload["value"])
    elif command == "dialplan.continue":
        path += "/continue"
        params = {
            "context": str(payload["context"]),
            "extension": str(payload["extension"]),
            "priority": "1",
        }
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
    return result

"""Exercise the deployed gateway against its configured Asterisk without logging keys."""

import argparse
import asyncio
import json
import os
from uuid import UUID, uuid4

import aiohttp
import websockets


async def request(
    session: aiohttp.ClientSession,
    method: str,
    url: str,
    **kwargs: object,
) -> object:
    async with session.request(method, url, **kwargs) as response:
        if response.status >= 400:
            raise RuntimeError(f"{method} {url} returned {response.status}")
        return await response.json() if response.status != 204 else None


async def run(args: argparse.Namespace) -> None:
    email = os.environ["GATEWAY_TEST_EMAIL"]
    password = os.environ["GATEWAY_TEST_PASSWORD"]
    key_id = None
    previous_destinations: list[str] = []
    previous_scopes: list[str] = []
    async with aiohttp.ClientSession(
        cookie_jar=aiohttp.CookieJar(unsafe=True), headers={"Origin": args.origin}
    ) as http:
        session_data = await request(
            http,
            "POST",
            f"{args.http_url}/api/v1/auth/login",
            json={"email": email, "password": password},
        )
        organization_id = session_data["organization_id"]
        apps = await request(
            http,
            "GET",
            f"{args.http_url}/api/v1/organizations/{organization_id}/partner-apps",
        )
        app = next(item for item in apps if item["agent_slug"] == args.agent_slug)
        previous_destinations = app["allowed_destinations"]
        previous_scopes = app["scopes"]
        required_scopes = sorted(
            set(previous_scopes)
            | {"calls:hangup", "calls:originate", "calls:transfer", "media:stream"}
        )
        destination = f"{args.context}:{args.extension}"
        if destination not in previous_destinations or required_scopes != previous_scopes:
            await request(
                http,
                "PATCH",
                f"{args.http_url}/api/v1/partner-apps/{app['id']}",
                json={
                    "allowed_destinations": sorted(
                        set(previous_destinations) | {destination}
                    ),
                    "scopes": required_scopes,
                },
            )
        try:
            issued = await request(
                http,
                "POST",
                f"{args.http_url}/api/v1/partner-apps/{app['id']}/api-keys",
                json={"name": "ephemeral-live-pbx-probe", "scopes": required_scopes},
            )
            key_id = issued["id"]
            token_data = await request(
                http,
                "POST",
                f"{args.http_url}/api/v1/realtime/tokens",
                headers={"Authorization": f"Bearer {issued['key']}"},
            )
            await exercise_socket(args, token_data["token"])
        finally:
            if key_id:
                await request(
                    http,
                    "DELETE",
                    f"{args.http_url}/api/v1/api-keys/{key_id}",
                )
            if destination not in previous_destinations or required_scopes != previous_scopes:
                await request(
                    http,
                    "PATCH",
                    f"{args.http_url}/api/v1/partner-apps/{app['id']}",
                    json={
                        "allowed_destinations": previous_destinations,
                        "scopes": previous_scopes,
                    },
                )


async def exercise_socket(args: argparse.Namespace, token: str) -> None:
    frames: dict[str, int] = {}
    request_calls: dict[str, str] = {}
    ended: set[str] = set()
    hangup_sent: set[str] = set()
    first_call_id = ""
    transfer_started = False
    transfer_cancelled = False
    request_ids = [str(uuid4()) for _ in range(args.calls)]
    async with websockets.connect(f"{args.ws_url}/v1/realtime?token={token}") as socket:
        await socket.send(
            json.dumps(
                {
                    "type": "session.register",
                    "agent_slug": args.agent_slug,
                    "protocol_version": "1",
                }
            )
        )
        ready = json.loads(await asyncio.wait_for(socket.recv(), 5))
        assert ready["type"] == "session.ready"
        for index, request_id in enumerate(request_ids):
            originate = {
                "type": "outbound.originate",
                "request_id": request_id,
                "payload": {
                    "context": args.context,
                    "extension": args.extension,
                    "timeout": 20,
                },
            }
            await socket.send(json.dumps(originate))
            if index == 0:
                await socket.send(json.dumps(originate))
        deadline = asyncio.get_running_loop().time() + args.timeout
        while asyncio.get_running_loop().time() < deadline:
            message = await asyncio.wait_for(socket.recv(), 5)
            if isinstance(message, bytes):
                frame_call_id = str(UUID(bytes=message[:16]))
                if frame_call_id in frames:
                    frames[frame_call_id] += 1
                    await socket.send(message)
                transfer_ready = frame_call_id != first_call_id or transfer_cancelled
                if (
                    frames.get(frame_call_id, 0) >= args.minimum_frames
                    and transfer_ready
                    and frame_call_id not in hangup_sent
                ):
                    await send_control(socket, frame_call_id, "call.hangup")
                    hangup_sent.add(frame_call_id)
                continue
            event = json.loads(message)
            if event["type"] == "outbound.accepted":
                request_id = event.get("request_id", "")
                if request_id in request_calls and request_calls[request_id] != event["call_id"]:
                    raise AssertionError("Idempotent originate created two calls")
                request_calls[request_id] = event["call_id"]
                first_call_id = first_call_id or event["call_id"]
            elif event["type"] == "call.started" and not transfer_started:
                first_call_id = first_call_id or event["call_id"]
                frames[event["call_id"]] = 0
                await send_control(
                    socket,
                    event["call_id"],
                    "transfer.attended",
                    {"context": args.context, "extension": args.extension},
                )
                transfer_started = True
            elif event["type"] == "call.started":
                frames[event["call_id"]] = 0
            elif event["type"] == "transfer.consulting":
                await send_control(socket, first_call_id, "transfer.cancel")
                transfer_cancelled = True
            elif event["type"] == "call.ended":
                ended.add(event["call_id"])
                if len(ended) == args.calls:
                    break
            elif event["type"] == "error":
                raise RuntimeError(f"Gateway error {event['code']}: {event['message']}")
        if len(frames) != args.calls or any(
            count < args.minimum_frames for count in frames.values()
        ):
            raise AssertionError(
                f"Expected {args.minimum_frames} frames on {args.calls} calls, got {frames}"
            )
        if not transfer_cancelled:
            raise AssertionError("Attended transfer consult/cancel was not completed")
        print(
            json.dumps(
                {
                    "status": "passed",
                    "calls": args.calls,
                    "audio_frames": frames,
                    "idempotency": "passed",
                    "attended_transfer_cancel": "passed",
                }
            )
        )


async def send_control(
    socket: websockets.ClientConnection,
    call_id: str,
    command: str,
    payload: dict[str, object] | None = None,
) -> None:
    await socket.send(
        json.dumps(
            {
                "type": "call.control",
                "request_id": str(uuid4()),
                "call_id": call_id,
                "command": command,
                "payload": payload or {},
            }
        )
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--http-url", default="http://127.0.0.1:8080")
    parser.add_argument("--ws-url", default="ws://127.0.0.1:8080")
    parser.add_argument("--agent-slug", default="demo-agent")
    parser.add_argument("--origin", default="http://localhost:5173")
    parser.add_argument("--context", default="from-internal-custom")
    parser.add_argument("--extension", default="9899")
    parser.add_argument("--minimum-frames", type=int, default=50)
    parser.add_argument("--calls", type=int, default=1)
    parser.add_argument("--timeout", type=int, default=30)
    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(run(parse_args()))

"""Exercise durable SDK reads against real calls, including an API restart.

Run inside the API container with the SDK installed and signals probe adjacent.
The before phase saves an expiring probe key in a mode-0600 state file. Run
after following an API restart, then cleanup even if verification fails.
"""

import argparse
import asyncio
import importlib.util
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import aiohttp
from app.settings import get_settings
from asterisk_ai_gateway import GatewayClient, GatewayHTTPError

spec = importlib.util.spec_from_file_location(
    "signals_probe", Path(__file__).with_name("live-call-signals-probe.py")
)
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


async def login(http, base):
    settings = get_settings()
    return await probe.request(http, "POST", base, "/api/v1/auth/login", json={
        "email": settings.bootstrap_email, "password": settings.bootstrap_password,
    })


def save(path, state):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w") as output:
        os.fchmod(output.fileno(), 0o600)
        json.dump(state, output)


async def collect(client):
    items, cursor = [], None
    while True:
        page = await client.list_calls(limit=2, cursor=cursor)
        items.extend(page["items"])
        cursor = page["next_cursor"]
        if cursor is None:
            return items


async def verify(base, state):
    own = GatewayClient(base, state["keys"][0]["key"], state["slug"])
    other = GatewayClient(base, state["keys"][1]["key"], state["other_slug"])
    calls = await collect(own)
    assert {call["call_id"] for call in calls} == set(state["call_ids"])
    for call in calls:
        assert call["source"] == "gateway" and call["history_complete"]
        assert call["terminal"]
        assert await own.get_call(call["call_id"]) == call
        signals, cursor = [], None
        while True:
            page = await own.list_call_signals(call["call_id"], limit=1, cursor=cursor)
            signals.extend(page["items"])
            cursor = page["next_cursor"]
            if cursor is None:
                break
        assert [item["sequence"] for item in signals] == list(range(1, call["sequence"] + 1))
        assert [item["status"] for item in signals] == state["states"][call["call_id"]]
        assert signals[-1]["status"] == call["status"]
        for read in (other.get_call, other.list_call_signals):
            try:
                await read(call["call_id"])
            except GatewayHTTPError as error:
                assert error.status == 404
            else:
                raise AssertionError("Another app read a private call")
    assert (await other.list_calls())["items"] == []
    return calls


async def run(args):
    base = args.base_url.rstrip("/")
    path = Path(args.state)
    settings = get_settings()
    state = json.loads(path.read_text()) if path.exists() else {"apps": [], "keys": []}
    async with aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar(unsafe=True),
                                     headers={"Origin": settings.web_origin}) as http:
        user = await login(http, base)
        if args.phase == "before":
            assert not state["apps"], "Clean the previous probe before starting another"
            suffix = uuid4().hex[:12]
            state.update(slug="history-probe-" + suffix, other_slug="history-other-" + suffix)
            for slug in (state["slug"], state["other_slug"]):
                scopes = ["calls:read", "calls:originate", "calls:hangup", "media:stream"]
                app = await probe.request(http, "POST", base,
                    f"/api/v1/organizations/{user['organization_id']}/partner-apps", json={
                        "name": "Ephemeral history verification", "agent_slug": slug,
                        "scopes": scopes, "allowed_destinations": [
                            f"{args.context}:{extension}" for extension in
                            ["answer", "ring", "busy", "reject", "unavailable", "failed"]],
                    })
                state["apps"].append(app["id"])
                save(path, state)
                key = await probe.request(http, "POST", base,
                    f"/api/v1/partner-apps/{app['id']}/api-keys", json={
                        "name": "Ephemeral history verification", "scopes": scopes,
                        "expires_at": (datetime.now(UTC) + timedelta(minutes=45)).isoformat(),
                    })
                state["keys"].append(key)
                save(path, state)
            token = await probe.request(http, "POST", base, "/api/v1/realtime/tokens",
                headers={"Authorization": "Bearer " + state["keys"][0]["key"]})
            results = await probe.exercise(http, base, token["token"], state["slug"], args.context)
            state["call_ids"] = [item["call_id"] for item in results]
            state["states"] = {item["call_id"]: item["states"] for item in results}
            save(path, state)
            state["calls"] = await verify(base, state)
            save(path, state)
            imported = await probe.request(http, "GET", base, "/api/v1/call-history?limit=100")
            print(json.dumps({"phase": "before", "calls": len(results), "sdk": "passed",
                              "ownership": "passed", "cms_page": len(imported["items"])}))
        elif args.phase == "after":
            assert await verify(base, state) == state["calls"], "History changed across restart"
            print(json.dumps({"phase": "after", "restart_persistence": "passed",
                              "calls": len(state["call_ids"])}))
        else:
            for key in state["keys"]:
                await probe.request(http, "DELETE", base, f"/api/v1/api-keys/{key['id']}")
            if state["keys"]:
                client = GatewayClient(base, state["keys"][0]["key"], state["slug"])
                try:
                    await client.list_calls()
                except GatewayHTTPError as error:
                    assert error.status == 401
                else:
                    raise AssertionError("Revoked key still reads calls")
            for app_id in state["apps"]:
                await probe.request(http, "DELETE", base, f"/api/v1/partner-apps/{app_id}")
            path.unlink(missing_ok=True)
            print(json.dumps({"phase": "cleanup", "revoked_key": "denied", "status": "passed"}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://admin-ui")
    parser.add_argument("--context", default="gateway-signals-20261020")
    parser.add_argument("--state", default="/tmp/gateway-history-probe-state.json")
    parser.add_argument("--phase", choices=["before", "after", "cleanup"], required=True)
    asyncio.run(run(parser.parse_args()))

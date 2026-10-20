"""Verify real PBX signals through the partner proxy; never print credentials.

Run inside the deployed API container. The operator must provision an isolated
context with answer/ring/busy/reject/unavailable/failed test extensions first.
Credentials come from the existing deployment settings, as in the PBX runbook.
"""

import argparse
import asyncio
import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import aiohttp
from app.settings import get_settings


async def request(http, method, base, path, **kwargs):
    async with http.request(method, base + path, **kwargs) as response:
        if response.status >= 400:
            raise RuntimeError(f"Probe {method} {path} returned {response.status}")
        return await response.json() if response.status != 204 else None


async def exercise(http, base, token, slug, context):
    results = []
    async with http.ws_connect(base + "/v1/realtime", params={"token": token}) as ws:
        await ws.send_json({"type": "session.register", "agent_slug": slug, "protocol_version": "1"})
        assert (await ws.receive_json())["type"] == "session.ready"
        scenarios = [
            ("busy", "busy", 5), ("reject", "rejected", 5),
            ("unavailable", "unavailable", 5), ("failed", "failed", 5),
            ("ring", "no_answer", 2), ("ring", "cancelled", 10),
            ("answer", "completed", 10), ("answer", "completed", 10),
        ]
        for index, (extension, expected, timeout) in enumerate(scenarios):
            request_id = str(uuid4())
            await ws.send_json({
                "type": "outbound.originate", "request_id": request_id,
                "payload": {"context": context, "extension": extension, "timeout": timeout},
            })
            call_id = None
            states, frames, started, control_sent = [], 0, False, False
            active_query_id, active_sequence = None, None
            active_query_passed = False
            deadline = asyncio.get_running_loop().time() + 20
            while asyncio.get_running_loop().time() < deadline:
                message = await asyncio.wait_for(ws.receive(), 15)
                if message.type == aiohttp.WSMsgType.BINARY:
                    frames += 1
                    await ws.send_bytes(message.data)
                    continue
                if message.type != aiohttp.WSMsgType.TEXT:
                    raise AssertionError("Partner socket closed during probe")
                event = json.loads(message.data)
                if event["type"] == "error":
                    raise AssertionError(f"Partner error: {event['code']}")
                if event["type"] == "outbound.accepted":
                    assert event["request_id"] == request_id
                    call_id = event["call_id"]
                elif event["type"] == "call.status":
                    assert call_id == event["call_id"], "Status preceded acceptance"
                    if active_query_id and event.get("request_id") == active_query_id:
                        assert event["status"] == "ringing" and not event["terminal"]
                        assert event["sequence"] == active_sequence
                        active_query_passed = True
                        await ws.send_json({"type": "outbound.cancel", "call_id": call_id})
                        control_sent = True
                        continue
                    states.append(event["status"])
                    if expected == "cancelled" and event["status"] == "ringing" and not control_sent:
                        active_query_id, active_sequence = str(uuid4()), event["sequence"]
                        await ws.send_json({"type": "call.control", "call_id": call_id,
                                            "command": "call.status", "request_id": active_query_id})
                elif event["type"] == "call.started":
                    assert "answered" in states
                    started = True
                    if index == 7 and not control_sent:
                        await ws.send_json({"type": "call.control", "call_id": call_id,
                                            "command": "call.hangup", "request_id": str(uuid4())})
                        control_sent = True
                elif event["type"] == "call.ended":
                    assert event["status"] == expected, event
                    assert event["answered"] == (expected == "completed"), event
                    assert started == (expected == "completed"), event
                    assert event["terminal"] and states[0] == "dialing"
                    assert states[-1] == expected
                    # Reuse the active query ID: a read must still return the
                    # new terminal state rather than the previous ringing one.
                    query_id = active_query_id or str(uuid4())
                    await ws.send_json({"type": "call.control", "call_id": call_id,
                                        "command": "call.status", "request_id": query_id})
                    while True:
                        reply = await asyncio.wait_for(ws.receive_json(), 5)
                        if reply.get("request_id") == query_id:
                            break
                        assert reply["type"] != "error", reply
                    assert reply == {**event, "type": "call.status", "request_id": query_id}
                    if index == 6:
                        assert frames > 0, "Answered call produced no audio"
                    if expected == "cancelled":
                        assert active_query_passed, "Ringing status query was not exercised"
                    results.append({"call_id": call_id,
                                    "extension": extension, "expected": expected, "states": states,
                                    "hangup_cause": event["hangup_cause"], "audio_frames": frames,
                                    "active_query": "passed" if active_query_passed else "not_requested",
                                    "completed_query": "passed"})
                    break
            else:
                raise AssertionError("Call did not reach call.ended")
        await ws.send_json({"type": "call.control", "call_id": str(uuid4()),
                            "command": "call.status", "request_id": str(uuid4())})
        assert (await ws.receive_json())["code"] == "command-failed"
    return results


async def main(args):
    settings = get_settings()
    base = args.base_url.rstrip("/")
    slug = "signals-probe-" + uuid4().hex[:12]
    scopes = ["calls:read", "calls:originate", "calls:hangup", "media:stream"]
    app_id = key_id = None
    async with aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar(unsafe=True),
                                     headers={"Origin": settings.web_origin}) as http:
        try:
            login = await request(http, "POST", base, "/api/v1/auth/login", json={
                "email": settings.bootstrap_email, "password": settings.bootstrap_password})
            partner = await request(http, "POST", base,
                                    f"/api/v1/organizations/{login['organization_id']}/partner-apps",
                                    json={"name": "Ephemeral call signals probe", "agent_slug": slug,
                                          "scopes": scopes, "allowed_destinations": [
                                              f"{args.context}:{extension}" for extension in
                                              ["answer", "ring", "busy", "reject", "unavailable", "failed"]]})
            app_id = partner["id"]
            issued = await request(http, "POST", base, f"/api/v1/partner-apps/{app_id}/api-keys",
                                   json={"name": "ephemeral-call-signals-probe", "scopes": scopes,
                                         "expires_at": (datetime.now(UTC) + timedelta(minutes=15)).isoformat()})
            key_id = issued["id"]
            token = await request(http, "POST", base, "/api/v1/realtime/tokens",
                                  headers={"Authorization": "Bearer " + issued["key"]})
            results = await exercise(http, base, token["token"], slug, args.context)
            runtime = await request(http, "GET", base, "/api/v1/runtime")
            assert runtime["active_calls"] == 0 and runtime["ari_connected"], runtime
            print(json.dumps({"status": "passed", "scenarios": results,
                              "active_calls": runtime["active_calls"], "ari_connected": True}))
        finally:
            if key_id:
                await request(http, "DELETE", base, f"/api/v1/api-keys/{key_id}")
            if app_id:
                await request(http, "DELETE", base, f"/api/v1/partner-apps/{app_id}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://admin-ui")
    parser.add_argument("--context", required=True)
    asyncio.run(main(parser.parse_args()))

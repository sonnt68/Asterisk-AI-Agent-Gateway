"""Probe existing DID routes and shared caller IDs without changing inbound owners.

Run inside the deployed API container. Carrier calls require --carrier and use
the supplied managed-number cycle or an explicitly authorized --destination.
Secrets remain in memory. Only this run's grants, sessions and keys are removed.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import importlib.util
import json
import math
import struct
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import aiohttp
from app.settings import get_settings
from yarl import URL

spec = importlib.util.spec_from_file_location(
    "telephony_probe", Path(__file__).with_name("live-telephony-probe.py")
)
probe = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = probe
spec.loader.exec_module(probe)

SCOPES = ["calls:read", "media:stream", "calls:originate", "calls:hangup"]


async def next_event(session, predicate, timeout=20):
    deadline = asyncio.get_running_loop().time() + timeout
    while True:
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            raise probe.ProbeFailure("partner_event_timeout")
        message = await asyncio.wait_for(session.messages.get(), remaining)
        if message is None:
            raise probe.ProbeFailure("partner_socket_closed")
        data = probe.event_data(message)
        if data and data.get("type") == "error":
            raise probe.ProbeFailure("partner_protocol_error")
        if data and predicate(data):
            return data


def drain(sessions):
    for session in sessions:
        while not session.messages.empty():
            session.messages.get_nowait()


async def send_tone(session, call_id):
    """Send a brief 440 Hz PCM signal so silent test peers produce real media."""
    for frame in range(100):
        pcm = b"".join(struct.pack("<h", int(3000 * math.sin(2 * math.pi * 440 * (frame * 160 + n) / 8000))) for n in range(160))
        await session.socket.send(UUID(call_id).bytes + pcm)
        await asyncio.sleep(0.02)


async def wait_signal(session, call_id):
    deadline = asyncio.get_running_loop().time() + 8
    while asyncio.get_running_loop().time() < deadline:
        message = await asyncio.wait_for(session.messages.get(), max(0.1, deadline - asyncio.get_running_loop().time()))
        if message is None:
            raise probe.ProbeFailure("partner_socket_closed")
        data = probe.event_data(message)
        if data and data.get("type") == "error":
            raise probe.ProbeFailure("partner_protocol_error")
        if isinstance(message, bytes) and message[:16] == UUID(call_id).bytes:
            pcm = message[16:]
            if len(pcm) >= 2 and any(abs(v[0]) > 100 for v in struct.iter_unpack("<h", pcm)):
                return
    raise probe.ProbeFailure("non_silent_pcm_timeout")


async def run(args):
    settings = get_settings()
    api_base = args.base_url.rstrip("/") + "/api/v1"
    origin = settings.web_origin
    ari_base = settings.ari_base_url.rstrip("/")
    keys, fixture_ids, sessions, grants = [], [], [], []
    results = {"internal_inbound": [], "shared_outbound_internal": [], "carrier": []}
    cookie = probe.operator_browser_cookie(settings.freepbx_operator_organization_id)
    async with aiohttp.ClientSession(
        cookie_jar=aiohttp.CookieJar(unsafe=True),
        headers={"Origin": origin},
        timeout=aiohttp.ClientTimeout(total=15),
    ) as http, aiohttp.ClientSession(
        auth=aiohttp.BasicAuth(settings.ari_username, settings.ari_password),
        timeout=aiohttp.ClientTimeout(total=15),
    ) as ari:
        http.cookie_jar.update_cookies(
            {"gateway_session": cookie}, response_url=URL(args.base_url)
        )

        async def api(method, path, payload=None, expected={200}, headers=None):
            return await probe.api_request(
                http, method, api_base, path, stage=method + "_" + path.split("/")[1],
                payload=payload, expected=expected, headers=headers,
            )

        async def open_app(app, scopes):
            connected = await api("GET", "/connections")
            probe.require(
                not any(c.get("agent_slug") == app["agent_slug"] for c in connected),
                "existing_agent_connected",
            )
            key = await api("POST", f"/partner-apps/{app['id']}/api-keys", {
                "name": "Shared routing verification " + suffix,
                "scopes": scopes,
                "expires_at": (datetime.now(UTC) + timedelta(minutes=10)).isoformat(),
            }, {201})
            keys.append(key["id"])
            token = await api("POST", "/realtime/tokens", headers={
                "Authorization": "Bearer " + key["key"],
            })
            session = await probe.PartnerSession.open(
                args.base_url.replace("http://", "ws://").replace("https://", "wss://"),
                origin, app["agent_slug"], token["token"],
            )
            sessions.append(session)
            return session

        async def hangup(session, call_id):
            await session.socket.send(json.dumps({
                "type": "call.control", "command": "call.hangup", "call_id": call_id,
                "request_id": uuid4().hex, "payload": {},
            }))

        async def cleanup_channels():
            # Never terminate unrelated channels, including a concurrent real call.
            await probe.wait_clean(http, api_base, ari, ari_base, None)

        suffix = uuid4().hex[:10]
        try:
            runtime = await api("GET", "/runtime")
            probe.require(runtime["active_calls"] == 0, "initial_calls_not_zero")
            channels = await probe.ari_request(ari, ari_base, "GET", "/channels", stage="initial_channels")
            probe.require(not channels, "initial_channels_not_zero")
            phones = await api("GET", "/phone-numbers")
            by_number = {p["number"]: p for p in phones}
            selected = [by_number[n] for n in args.numbers.split(",")]
            probe.require(len(selected) == 4 and len({p['number'] for p in selected}) == 4, "four_exact_numbers")
            probe.require(not args.destination or (
                args.carrier and args.carrier_only and args.destination.isdigit()
            ), "external_destination_requires_carrier_only")
            probe.require(all(p["enabled"] and p["pbx_applied"] for p in selected), "number_not_enabled_applied")
            apps = await api("GET", f"/organizations/{settings.freepbx_operator_organization_id}/partner-apps")
            by_app = {a["id"]: a for a in apps}
            inbound = {}
            for phone in ([] if args.destination else selected):
                app_id = phone["partner_app_id"]
                if app_id not in inbound:
                    app = by_app[app_id]
                    probe.require(app["enabled"], "inbound_app_disabled")
                    inbound[app_id] = await open_app(app, ["calls:read", "media:stream"])
            for phone in ([] if args.carrier_only else selected):
                expected = inbound[phone["partner_app_id"]]
                other = next(s for s in inbound.values() if s is not expected)
                drain(sessions)
                try:
                    outer = await probe.originate(ari, ari_base, phone["number"], "existing_did")
                    call_id, _ = await probe.wait_for_start(expected, other)
                    await probe.ari_request(ari, ari_base, "POST", f"/channels/{outer}/play", stage="long_playback", expected={200, 201}, params={"media": "sound:demo-congrats"})
                    await probe.wait_for_binary(expected, call_id)
                    await probe.delete_channel(ari, ari_base, outer)
                    await probe.wait_for_end(expected, other, call_id)
                    await cleanup_channels()
                    row = {"number": phone["number"], "agent_slug": expected.slug, "result": "passed", "pcm": True}
                except Exception as error:
                    row = {"number": phone["number"], "result": "failed", "stage": str(error) if isinstance(error, probe.ProbeFailure) else type(error).__name__}
                    if "outer" in locals():
                        await probe.delete_channel(ari, ari_base, outer)
                    await cleanup_channels()
                results["internal_inbound"].append(row)
                print(json.dumps({"internal_inbound": row}), flush=True)

            outbound = []
            allowed = ["from-internal:*43"] + ["from-internal:" + p["number"] for p in selected]
            if args.destination:
                allowed.append("from-internal:" + args.destination)
            for index in range(2):
                app = await api("POST", f"/organizations/{settings.freepbx_operator_organization_id}/partner-apps", {
                    "name": "Shared routing verification " + str(index + 1),
                    "agent_slug": f"routing-verify-{index}-{suffix}",
                    "scopes": SCOPES, "allowed_destinations": allowed,
                }, {201})
                fixture_ids.append(app["id"])
                outbound.append(await open_app(app, SCOPES))
            for phone in selected:
                original = phone["outbound_partner_app_ids"]
                await api("PATCH", f"/phone-numbers/{phone['id']}", {
                    "outbound_partner_app_ids": original + fixture_ids,
                })
                grants.append(phone["id"])

            async def outbound_call(source, destination, session, receiver=None):
                drain(sessions)
                request_id = uuid4().hex
                try:
                    await session.socket.send(json.dumps({
                        "type": "outbound.originate", "request_id": request_id,
                        "payload": {"context": "from-internal", "extension": destination,
                                    "caller_number": source, "timeout": 30 if args.destination else 15},
                    }))
                    accepted = await next_event(session, lambda d: d.get("type") == "outbound.accepted" and d.get("request_id") == request_id)
                except Exception:
                    # The originate may have succeeded before its reply was lost.
                    # Disconnect only this fixture so Gateway releases its calls.
                    await session.close()
                    await cleanup_channels()
                    raise
                call_id = accepted["call_id"]
                row = {"source": source, "destination": destination, "call_id": call_id}
                owned_ids = []
                try:
                    channels = await probe.ari_request(ari, ari_base, "GET", "/channels", stage="accepted_channel_read")
                    owned_ids = [c["id"] for c in channels if c.get("name", "").startswith("Local/" + destination + "@") and c.get("caller", {}).get("number") == source]
                    started = await next_event(session, lambda d: d.get("call_id") == call_id and (d.get("type") == "call.started" or d.get("terminal") is True), 40 if args.destination else 20)
                    if started.get("terminal"):
                        row.update({k: started.get(k) for k in ("status", "reason", "hangup_cause", "dial_status", "answered")})
                        row["result"] = "failed"
                        return row
                    channels = await probe.ari_request(ari, ari_base, "GET", "/channels", stage="outbound_channel_read")
                    local_callers = [c.get("caller", {}).get("number") for c in channels if c.get("name", "").startswith("Local/" + destination + "@")]
                    probe.require(source in local_callers, "selected_caller_id_not_observed")
                    row["caller_id"] = source
                    row["signaling"] = "passed"
                    row["pjsip_peers"] = [{"name": c["name"], "caller": c.get("caller", {}).get("number"), "state": c.get("state")} for c in channels if c.get("name", "").startswith("PJSIP/")]
                    if receiver:
                        incoming = await next_event(receiver, lambda d: d.get("type") == "call.started", 5)
                        row["inbound_agent"] = receiver.slug
                        row["inbound_caller"] = incoming.get("caller", {}).get("number")
                        media = await asyncio.gather(
                            wait_signal(receiver, incoming["call_id"]),
                            wait_signal(session, call_id),
                            send_tone(session, call_id),
                            send_tone(receiver, incoming["call_id"]),
                            return_exceptions=True,
                        )
                        row["media_forward"] = not isinstance(media[0], BaseException)
                        row["media_reverse"] = not isinstance(media[1], BaseException)
                        row["rtp_statistics"] = []
                        for channel in channels:
                            if channel.get("name", "").startswith("PJSIP/"):
                                with contextlib.suppress(Exception):
                                    # Send two seconds and require at least one second
                                    # of native RTP in each direction. Observe counters
                                    # for up to 0.5 s after partner writes finish.
                                    for attempt in range(11):
                                        stats = await probe.ari_request(ari, ari_base, "GET", f"/channels/{channel['id']}/rtp_statistics", stage="native_rtp_statistics")
                                        if stats.get("txcount", 0) >= 50 and stats.get("rxcount", 0) >= 50:
                                            break
                                        if attempt < 10:
                                            await asyncio.sleep(0.05)
                                    row["rtp_statistics"].append({"name": channel["name"], "statistics": stats})
                        probe.require(row["media_forward"] and row["media_reverse"], "carrier_pcm_missing")
                        probe.require(len(row["rtp_statistics"]) == 2 and all(
                            leg["statistics"].get("txcount", 0) >= 50
                            and leg["statistics"].get("rxcount", 0) >= 50
                            and leg["statistics"].get("txploss", 0) == 0
                            and leg["statistics"].get("rxploss", 0) == 0
                            for leg in row["rtp_statistics"]
                        ), "carrier_rtp_incomplete")
                    elif args.destination:
                        async def external_signal():
                            # A handset can report answer before its speaker path
                            # is audible; give this human listening probe a lead-in.
                            row["tone_delay_seconds"] = 3
                            await asyncio.sleep(3)
                            await send_tone(session, call_id)
                            if args.external_prompt:
                                await asyncio.sleep(1)
                                primary = next(c["id"] for c in channels if c.get("name", "").startswith("Local/" + destination + "@") and c["name"].endswith(";1"))
                                await probe.ari_request(ari, ari_base, "POST", f"/channels/{primary}/play", stage="native_handset_playback", expected={200, 201}, params={"media": "sound:demo-congrats"})
                                row["native_playback_started"] = True
                                await asyncio.sleep(8)
                                await send_tone(session, call_id)

                        media = await asyncio.gather(
                            wait_signal(session, call_id), external_signal(),
                            return_exceptions=True,
                        )
                        row["media_from_phone"] = not isinstance(media[0], BaseException)
                        row["test_tone_sent"] = not isinstance(media[1], BaseException)
                        await asyncio.sleep(3)
                        row["rtp_statistics"] = []
                        for channel in channels:
                            if channel.get("name", "").startswith("PJSIP/"):
                                with contextlib.suppress(Exception):
                                    stats = await probe.ari_request(ari, ari_base, "GET", f"/channels/{channel['id']}/rtp_statistics", stage="external_rtp_statistics")
                                    row["rtp_statistics"].append({"name": channel["name"], "statistics": stats})
                        probe.require(row["test_tone_sent"], "external_signal_failed")
                    else:
                        await send_tone(session, call_id)
                        await wait_signal(session, call_id)
                    row.update({"result": "passed", "answered": True, "pcm": True})
                    if args.destination:
                        row["result"] = "requires_handset_confirmation"
                        row["pcm"] = row["media_from_phone"]
                    await hangup(session, call_id)
                    return row
                except Exception as error:
                    row.update({"result": "failed", "stage": str(error) if isinstance(error, probe.ProbeFailure) else type(error).__name__})
                    return row
                finally:
                    with contextlib.suppress(Exception):
                        await hangup(session, call_id)
                    for channel_id in owned_ids:
                        with contextlib.suppress(Exception):
                            await probe.delete_channel(ari, ari_base, channel_id)
                    await asyncio.sleep(0.5)
                    await cleanup_channels()

            for phone in ([] if args.carrier_only else selected):
                for session in outbound:
                    try:
                        row = await outbound_call(phone["number"], "*43", session)
                    except Exception as error:
                        row = {"source": phone["number"], "result": "failed", "stage": str(error) if isinstance(error, probe.ProbeFailure) else type(error).__name__}
                    row["outbound_agent"] = session.slug
                    results["shared_outbound_internal"].append(row)
                    print(json.dumps({"shared_outbound_internal": row}), flush=True)
            if args.carrier:
                for index, source in enumerate(selected[:args.carrier_limit]):
                    target = selected[(index + 1) % len(selected)]
                    try:
                        destination = args.destination or target["number"]
                        receiver = None if args.destination else inbound[target["partner_app_id"]]
                        row = await outbound_call(source["number"], destination, outbound[index % 2], receiver)
                    except Exception as error:
                        row = {"source": source["number"], "destination": args.destination or target["number"], "result": "failed", "stage": str(error) if isinstance(error, probe.ProbeFailure) else type(error).__name__}
                    results["carrier"].append(row)
                    print(json.dumps({"carrier": row}), flush=True)
        finally:
            failures = []
            for phone_id in grants:
                try:
                    current = await api("GET", "/phone-numbers")
                    phone = next(p for p in current if p["id"] == phone_id)
                    await api("PATCH", f"/phone-numbers/{phone_id}", {
                        "outbound_partner_app_ids": [a for a in phone["outbound_partner_app_ids"] if a not in fixture_ids],
                    })
                except Exception:
                    failures.append("assignment_cleanup")
            for session in sessions:
                await session.close()
            try:
                await cleanup_channels()
            except Exception:
                failures.append("call_cleanup")
            for key_id in keys:
                try:
                    await api("DELETE", f"/api-keys/{key_id}", expected={204})
                except Exception:
                    failures.append("key_cleanup")
            for app_id in fixture_ids:
                try:
                    await api("DELETE", f"/partner-apps/{app_id}", expected={204})
                except Exception:
                    failures.append("fixture_app_cleanup")
            results["cleanup"] = {"failures": failures, "temporary_keys": keys, "fixture_apps": fixture_ids}
            print(json.dumps({"cleanup": results["cleanup"]}), flush=True)
        results["runtime_after"] = await api("GET", "/runtime")
        return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--numbers", required=True)
    parser.add_argument("--carrier", action="store_true")
    parser.add_argument("--carrier-only", action="store_true")
    parser.add_argument("--destination", help="Explicit operator-authorized external destination")
    parser.add_argument("--external-prompt", action="store_true", help="Compare delayed partner tone with native Asterisk playback")
    parser.add_argument("--carrier-limit", type=int, choices=range(1, 5), default=4)
    try:
        print(json.dumps(asyncio.run(run(parser.parse_args()))), flush=True)
    except Exception as error:
        print(json.dumps({"fatal": str(error) if isinstance(error, probe.ProbeFailure) else type(error).__name__}), flush=True)
        raise SystemExit(1) from None

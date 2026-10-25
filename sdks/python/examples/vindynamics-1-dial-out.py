"""Vindynamics-1 Gateway example, based on the repository's dial_out.py.

Python 3.10+. Install the SDK using the same Python that runs this file:
    python3 -m pip install asterisk-ai-agent-gateway-sdk==0.4.0

Optional environment (URL and slug already default to the values below):
    export GATEWAY_URL=http://118.107.77.136:15173
    export GATEWAY_AGENT_SLUG=vindynamics-1

Set GATEWAY_API_KEY or enter it at the hidden prompt. Use the Vindynamics-1 key.
Check registration and heartbeat without dialling:
    python3 vindynamics-1-dial-out.py --check
Dial a number you are authorized to call (replace all Xs with digits):
    python3 vindynamics-1-dial-out.py 84XXXXXXXXX

Caller ID: 842444562933. Outbound context: from-internal.
The called party hears their own voice echoed through Gateway, not an AI.
The test hangs up 20 seconds after answering. No call is placed automatically.
Run only one process for this slug: a new session replaces the previous one.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import getpass
import logging
import os
import re

import aiohttp
from asterisk_ai_gateway import Audio, AuthenticationError, GatewayClient, GatewayError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
LOGGER = logging.getLogger("vindynamics-1-dial-out")

DEFAULT_GATEWAY_URL = "http://118.107.77.136:15173"
DEFAULT_GATEWAY_AGENT_SLUG = "vindynamics-1"
CALLER_NUMBER = "842444562933"

#: Long enough to hear yourself and know the media path works, short enough
#: that a forgotten run does not sit on a live trunk.
ECHO_SECONDS = 20


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("number", nargs="?", help="Destination number in 84... format")
    parser.add_argument("--check", action="store_true", help="Register and verify heartbeat; do not dial")
    args = parser.parse_args()
    if args.check and args.number:
        parser.error("Use --check without a destination number")
    if not args.check and not args.number:
        parser.error("Provide a destination number, or use --check")
    if args.number and not re.fullmatch(r"84[0-9]{7,13}", args.number):
        parser.error("Destination must contain digits in 84... format, without + or spaces")
    args.gateway_url = os.getenv("GATEWAY_URL", DEFAULT_GATEWAY_URL).strip().rstrip("/")
    args.agent_slug = os.getenv("GATEWAY_AGENT_SLUG", DEFAULT_GATEWAY_AGENT_SLUG).strip()
    if args.agent_slug != DEFAULT_GATEWAY_AGENT_SLUG:
        parser.error("This sample requires GATEWAY_AGENT_SLUG=vindynamics-1 and its matching API key")
    args.api_key = os.getenv("GATEWAY_API_KEY", "").strip()
    if not args.api_key:
        try:
            args.api_key = getpass.getpass("Vindynamics-1 API key (hidden): ").strip()
        except EOFError:
            parser.error("Set GATEWAY_API_KEY or enter the key in an interactive terminal")
    if not args.api_key.startswith("agw_live_"):
        parser.error("GATEWAY_API_KEY must be the agw_live_... key for Vindynamics-1")
    return args


async def main(args: argparse.Namespace) -> int:
    number = args.number
    context = "from-internal"

    client = GatewayClient(
        gateway_url=args.gateway_url,
        api_key=args.api_key,
        agent_slug=args.agent_slug,
        # One shot: a reconnect would re-register and dial nothing, which
        # reads as a hang rather than a failure.
        reconnect=False,
    )

    request_id: str | None = None
    hangup_timer: asyncio.Task[None] | None = None
    exit_code = 1
    answered = False
    ready = False

    async def hang_up_after(call_id: str) -> None:
        # A timer, not a frame counter: a silent callee sends no audio, and
        # the call would otherwise sit on a live trunk until someone noticed.
        await asyncio.sleep(ECHO_SECONDS)
        LOGGER.info("echoed for %ss, hanging up", ECHO_SECONDS)
        await client.hangup(call_id)

    try:
        async for item in client.stream():
            if isinstance(item, Audio):
                # Send it straight back, so the callee hearing themselves
                # proves the complete Gateway audio round trip.
                await client.send_audio(item.call_id, item.pcm)
                continue

            kind = item.get("type")

            if kind == "session.ready":
                ready = True
                LOGGER.info("session.ready: agent_slug=%s connection_id=%s", args.agent_slug, client.connection_id)
                if args.check:
                    continue
                request_id = await client.originate(context, number, timeout=30, caller_number=CALLER_NUMBER)
                LOGGER.info("dialling %s:%s request_id=%s", context, number, request_id)

            elif kind == "heartbeat.ack" and args.check and ready:
                LOGGER.info("heartbeat.ack: connection check passed; no call placed")
                exit_code = 0
                break

            elif kind == "outbound.accepted":
                # Acceptance does not establish ringing or an answer.
                LOGGER.info("Gateway accepted the request, call_id=%s", item["call_id"])

            elif kind == "call.started":
                media = item.get("media", {})
                # The rate is announced per call. Never assume one.
                LOGGER.info(
                    "answered %s at %s Hz, %s",
                    item["call_id"],
                    media.get("sample_rate"),
                    media.get("encoding"),
                )
                if not args.check:
                    answered = True
                    hangup_timer = asyncio.create_task(hang_up_after(item["call_id"]))

            elif kind == "call.ended":
                LOGGER.info("call ended %s", item["call_id"])
                exit_code = 0 if answered else 1
                break

            elif kind == "error":
                LOGGER.error("gateway error [%s] %s", item.get("code"), item.get("message"))
                if item.get("code") == "outbound-failed":
                    LOGGER.error(
                        "Gateway refused the outbound request, so retrying "
                        "will not help. Ask the operator to confirm both: that "
                        "'%s:%s' is accepted by the partner app allowlist, and that "
                        "'%s' is a context with an outbound route.",
                        context,
                        number,
                        context,
                    )
                break

    except AuthenticationError as error:
        # Terminal by definition: the key is revoked, expired, or its app is off.
        LOGGER.error("%s", error)
    except (GatewayError, aiohttp.ClientError, OSError) as error:
        # Do not log exception URLs: a WebSocket URL can contain its token.
        LOGGER.error("Connection failed (%s); check URL, key and agent slug", type(error).__name__)
    finally:
        if hangup_timer is not None:
            hangup_timer.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await hangup_timer
        # Closing hangs up whatever this connection still owns.
        await client.close()

    return exit_code


async def run(args: argparse.Namespace) -> int:
    if args.check:
        try:
            return await asyncio.wait_for(main(args), timeout=30)
        except asyncio.TimeoutError:  # noqa: UP041 -- Python 3.10 uses a distinct asyncio exception.
            LOGGER.error("No successful registration and heartbeat within 30 seconds")
            return 1
    return await main(args)


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(run(arguments())))
    except KeyboardInterrupt:
        LOGGER.info("Stopped")

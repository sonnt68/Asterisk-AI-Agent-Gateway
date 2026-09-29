"""Dial a PSTN number and echo the callee back to themselves.

    export GATEWAY_URL=https://gateway.example.com
    export GATEWAY_API_KEY=agw_live_...
    export GATEWAY_AGENT_SLUG=support-agent
    export OUTBOUND_CONTEXT=from-internal
    python examples/dial_out.py 84969097109

Two things have to be true before this rings, and only the first one produces
an error you can see: the destination must be allowlisted on the partner app
(outbound PSTN needs a prefix rule such as `from-internal:84*`, since the
callee differs per call), and the context must be one that actually routes a
number outward. Origination dials `Local/<extension>@<context>`, so an inbound
trunk context matches incoming DIDs and routes nothing out — it passes the
allowlist and then fails inside the dialplan.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys

from asterisk_ai_gateway import Audio, AuthenticationError, GatewayClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
LOGGER = logging.getLogger("dial-out")

DEFAULT_NUMBER = "84969097109"

#: Long enough to hear yourself and know the media path works, short enough
#: that a forgotten run does not sit on a live trunk.
ECHO_SECONDS = 30


async def main() -> int:
    number = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_NUMBER
    context = os.environ.get("OUTBOUND_CONTEXT", "from-internal")

    client = GatewayClient(
        gateway_url=os.environ["GATEWAY_URL"],
        api_key=os.environ["GATEWAY_API_KEY"],
        agent_slug=os.environ.get("GATEWAY_AGENT_SLUG") or os.environ.get("AGENT_SLUG", "support-agent"),
        # One shot: a reconnect would re-register and dial nothing, which
        # reads as a hang rather than a failure.
        reconnect=False,
    )

    request_id: str | None = None
    hangup_timer: asyncio.Task[None] | None = None
    exit_code = 1

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
                # proves partner -> gateway -> Asterisk and the return path.
                await client.send_audio(item.call_id, item.pcm)
                continue

            kind = item.get("type")

            if kind == "session.ready":
                LOGGER.info("registered as %s", client.connection_id)
                request_id = await client.originate(context, number, timeout=45)
                LOGGER.info("dialling %s:%s request_id=%s", context, number, request_id)

            elif kind == "outbound.accepted":
                # Accepted is not answered. Nothing is live until call.started.
                LOGGER.info("Asterisk took the request, call_id=%s — ringing", item["call_id"])

            elif kind == "call.started":
                media = item.get("media", {})
                # The rate is announced per call. Never assume one.
                LOGGER.info(
                    "answered %s at %s Hz, %s",
                    item["call_id"],
                    media.get("sample_rate"),
                    media.get("encoding"),
                )
                hangup_timer = asyncio.create_task(hang_up_after(item["call_id"]))

            elif kind == "call.ended":
                LOGGER.info("call ended %s", item["call_id"])
                exit_code = 0
                break

            elif kind == "error":
                LOGGER.error("gateway error [%s] %s", item.get("code"), item.get("message"))
                if item.get("code") == "outbound-failed":
                    LOGGER.error(
                        "The gateway refused this before Asterisk saw it, so retrying "
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
    except KeyboardInterrupt:
        LOGGER.info("interrupted")
    finally:
        if hangup_timer is not None:
            hangup_timer.cancel()
        # Closing hangs up whatever this connection still owns.
        await client.close()

    return exit_code


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

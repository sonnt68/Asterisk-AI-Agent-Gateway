"""Place an outbound call, then echo the callee back to themselves.

Outbound is the one command with a destination you choose per call, so it is
where the allowlist is felt. Two things must be true before this rings, and
only the first announces itself:

  1. `<context>:<number>` is accepted by the partner app allowlist. PSTN needs
     a prefix rule such as `from-internal:84*`, since the callee changes every
     call. A miss returns `outbound-failed` before Asterisk is touched.
  2. The context routes a number outward. Origination dials
     `Local/<extension>@<context>`, so an inbound trunk context matches
     incoming DIDs and routes nothing out — it clears the allowlist and then
     fails inside the dialplan, with no error frame to read.

Both are the operator's to set. Settle them before writing code against them.

    pip install asterisk-ai-agent-gateway-sdk
    export GATEWAY_URL=https://gateway.example.com
    export GATEWAY_API_KEY=...          # from a secret store, not a file
    python dial_out.py 84900000000
"""

import asyncio
import os
import sys

from asterisk_ai_gateway import Audio, AuthenticationError, GatewayClient

NUMBER = sys.argv[1] if len(sys.argv) > 1 else "84900000000"
CONTEXT = os.environ.get("OUTBOUND_CONTEXT", "from-internal")
ECHO_SECONDS = 30

client = GatewayClient(
    gateway_url=os.environ["GATEWAY_URL"],
    api_key=os.environ["GATEWAY_API_KEY"],
    agent_slug="support-agent",
    # One shot. A reconnect would re-register and dial nothing, which reads as
    # a hang rather than a failure.
    reconnect=False,
)


async def hang_up_after(call_id: str) -> None:
    # A timer, not a frame count: a silent callee sends no audio, and the call
    # would otherwise sit on a live trunk until somebody noticed.
    await asyncio.sleep(ECHO_SECONDS)
    await client.hangup(call_id)


async def main() -> None:
    timer = None
    try:
        async for item in client.stream():
            if isinstance(item, Audio):
                await client.send_audio(item.call_id, item.pcm)
                continue

            kind = item["type"]
            if kind == "session.ready":
                await client.originate(CONTEXT, NUMBER, timeout=45)
                print("dialling", f"{CONTEXT}:{NUMBER}")
            elif kind == "outbound.accepted":
                # Accepted is not answered: Asterisk took the request, nothing more.
                print("ringing", item["call_id"])
            elif kind == "call.started":
                # The rate is announced per call. Never assume one.
                print("answered at", item["media"]["sample_rate"], "Hz")
                timer = asyncio.create_task(hang_up_after(item["call_id"]))
            elif kind == "call.ended":
                print("call down", item["call_id"])
                break
            elif kind == "error":
                print("gateway refused:", item["code"], item["message"])
                break
    except AuthenticationError as error:
        # Terminal: the key is revoked, expired, or its partner app is off.
        print(error)
    finally:
        if timer is not None:
            timer.cancel()
        # Closing hangs up whatever this connection still owns.
        await client.close()


asyncio.run(main())

"""Echo agent: proves both media directions in about forty lines.

    export GATEWAY_URL=https://gateway.example.com
    export GATEWAY_API_KEY=agw_live_...
    export AGENT_SLUG=support-agent
    python examples/echo_agent.py

Every frame the caller speaks is sent straight back, so hearing yourself
means audio flows partner -> gateway -> Asterisk and back.
"""

from __future__ import annotations

import asyncio
import logging
import os

from asterisk_ai_gateway import GatewayClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
LOGGER = logging.getLogger("echo-agent")


async def main() -> None:
    client = GatewayClient(
        gateway_url=os.environ["GATEWAY_URL"],
        api_key=os.environ["GATEWAY_API_KEY"],
        agent_slug=os.environ.get("AGENT_SLUG", "support-agent"),
    )

    async def on_event(event: dict) -> None:
        kind = event.get("type")
        if kind == "session.ready":
            LOGGER.info("registered as %s", client.connection_id)
        elif kind == "call.started":
            LOGGER.info("call up %s from %s", event["call_id"], event.get("caller"))
        elif kind == "dtmf.received":
            LOGGER.info("dtmf %s on %s", event["digit"], event["call_id"])
        elif kind == "call.ended":
            LOGGER.info("call down %s", event["call_id"])
        elif kind == "error":
            LOGGER.error("gateway error %s: %s", event["code"], event["message"])

    async def on_audio(call_id: str, pcm: bytes) -> None:
        await client.send_audio(call_id, pcm)

    await client.run(on_event=on_event, on_audio=on_audio)


if __name__ == "__main__":
    asyncio.run(main())

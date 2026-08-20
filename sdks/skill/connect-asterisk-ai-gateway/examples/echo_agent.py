"""A complete gateway agent, in as few lines as the protocol allows.

It echoes the caller back to themselves, which proves both audio directions
without needing a model. Replace `on_audio` with your own pipeline.

    pip install asterisk-ai-agent-gateway-sdk
    export GATEWAY_URL=https://gateway.example.com
    export GATEWAY_API_KEY=...          # from a secret store, not a file
    python echo_agent.py
"""

import asyncio
import os

from asterisk_ai_gateway import GatewayClient

client = GatewayClient(
    gateway_url=os.environ["GATEWAY_URL"],
    api_key=os.environ["GATEWAY_API_KEY"],
    agent_slug="support-agent",
)

# The rate is announced per call, so it belongs to the call, not to the module.
# A model that emits a fixed rate resamples against this number — and wants an
# integer ratio when it does. See references/audio.md.
rates: dict[str, int] = {}


async def on_event(event: dict) -> None:
    kind = event["type"]
    if kind == "call.started":
        rates[event["call_id"]] = event["media"]["sample_rate"]
        print("call up", event["call_id"], "at", event["media"]["sample_rate"], "Hz")
    elif kind == "call.ended":
        # Release everything call-local here, or the next call inherits it.
        rates.pop(event["call_id"], None)
        print("call down", event["call_id"])
    elif kind == "error":
        print("gateway refused:", event["code"], event["message"])


async def on_audio(call_id: str, pcm: bytes) -> None:
    """Mono PCM s16le at rates[call_id]. Send audio back the same way."""
    await client.send_audio(call_id, pcm)


asyncio.run(client.run(on_event=on_event, on_audio=on_audio))

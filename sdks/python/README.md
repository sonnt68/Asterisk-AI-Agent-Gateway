# Asterisk AI Agent Gateway — Python SDK

Realtime protocol v1 client. Exchanges your API key for a five-minute token,
registers the agent slug, heartbeats, reconnects with a fresh token, and hides
the 16-byte binary audio envelope.

```bash
pip install asterisk-ai-agent-gateway-sdk
```

```python
import asyncio, os
from asterisk_ai_gateway import GatewayClient

client = GatewayClient(
    gateway_url=os.environ["GATEWAY_URL"],
    api_key=os.environ["GATEWAY_API_KEY"],   # keep in a secret store
    agent_slug="support-agent",
)

async def on_event(event):
    if event["type"] == "call.started":
        await client.send_dtmf(event["call_id"], "1")   # needs calls:dtmf

async def on_audio(call_id, pcm):        # PCM s16le, 16 kHz, mono
    await client.send_audio(call_id, pcm)

asyncio.run(client.run(on_event=on_event, on_audio=on_audio))
```

Run one client per `agent_slug`: the gateway accepts a single live connection
per slug and answers a second one with `agent-in-use`.

`AuthenticationError` ends the stream and is never retried — the key is
revoked, expired, or its partner app is disabled. Every other transport
failure reconnects with exponential backoff up to `max_backoff`.

See `examples/echo_agent.py` and `docs/partner/integration-guide.html`.

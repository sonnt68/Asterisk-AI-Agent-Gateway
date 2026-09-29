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

async def on_audio(call_id, pcm):        # PCM s16le, mono, rate from call.started
    await client.send_audio(call_id, pcm)

asyncio.run(client.run(on_event=on_event, on_audio=on_audio))
```

Run one client per `agent_slug`: the gateway accepts a single live connection
per slug and answers a second one with `agent-in-use`.

`GatewayClient.run()` and `stream()` retry authentication failures three times
after the initial attempt (four attempts total). The shared budget covers token
exchange HTTP `401`/`403`, WebSocket handshake `401`/`403`, and close code
`4401`. Each retry exchanges the key for a fresh token after 1, 2, then 4
seconds, capped by `max_backoff`; the budget resets only after
`session.ready`. Set `reconnect=False` to disable retries; `close()` or task
cancellation stops pending retries. After the budget, `AuthenticationError`
ends the flow, and a revoked key cannot be revived. Direct
`realtime_token()` is a single request and does not retry itself. Other
transport failures reconnect with exponential backoff up to `max_backoff`.
Authentication and transport failures share that backoff, so preceding
transport failures can increase the next authentication retry's delay.

See `examples/echo_agent.py` and `docs/partner/integration-guide.html`.

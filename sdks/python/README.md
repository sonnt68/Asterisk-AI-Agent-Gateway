# AI Agent Gateway — Python SDK

Realtime protocol v1 client. Exchanges your API key for a five-minute token,
registers the agent slug, heartbeats, reconnects with a fresh token, and hides
the 16-byte binary audio envelope.

```bash
# Public realtime package (currently 0.3.2)
pip install asterisk-ai-agent-gateway-sdk==0.3.2
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

Run one client per `agent_slug`: the gateway keeps one live connection per
slug, and the most recent registration wins. A replaced client receives
close code `4409`, raises `SessionSupersededError`, and stops
without reconnecting; the gateway hangs up the calls it owned.

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

## Durable call history

The history-enabled SDK build exposes the durable history GET API. The current
published `0.3.2` package does not include these helpers; install the
operator-provided `0.4.0` wheel until publication is confirmed:

```bash
python -m pip install "https://gateway.example.com/downloads/sdk-0.4.0/asterisk_ai_agent_gateway_sdk-0.4.0-py3-none-any.whl"
```

Replace `gateway.example.com` with the artifact host supplied by the operator.
These async helpers send the long-lived API key directly as
`Authorization: Bearer`; they do not mint a realtime token, open a WebSocket,
or depend on a live session. The key needs the `calls:read` scope and is
restricted to its organization and partner app.

```python
async def read_history(call_id: str, next_cursor: str | None = None,
                       signal_cursor: str | None = None):
    page = await client.list_calls(
        limit=50,                         # 1..100; default 50
        cursor=next_cursor,               # omit on the first page
        agent_slug="support-agent",      # exact historic slug; omit for all
        status="completed",
        direction="outbound",
        started_after="2026-10-20T00:00:00Z",
        started_before="2026-10-21T00:00:00Z",
    )
    call = await client.get_call(call_id)
    signals = await client.list_call_signals(
        call_id,
        limit=50,                         # 1..100; default 50
        cursor=signal_cursor,
    )
    return page, call, signals
```

For numbered mode, omit `cursor` and pass a positive page number, for example
`numbered = await client.list_calls(agent_slug="support-agent", page=1)`.

`list_calls()` returns
`{"items": [...], "next_cursor": ..., "page": ..., "page_size": ..., "total": ..., "total_pages": ...}`;
the four numbered metadata fields are `null` in cursor mode. `get_call()` returns one call
summary, and `list_call_signals()` returns its `items` plus `next_cursor`.
Pass a positive integer `page` to use numbered pagination instead of `cursor`;
the Gateway rejects both together with `422`, returns `next_cursor: null` in
page mode, and reports `page_size`, `total`, and `total_pages` (with
`total_pages >= 1` even for an empty result). Timestamps must include an ISO
8601 timezone. Call summaries are newest first; signals are oldest first by
`sequence`. Numbered pages can shift when new calls arrive, so use cursor mode
for reliable iteration.

History contains metadata and normalized status signals only. It does not store
audio, transcripts, or phone numbers, and records have no automatic deletion.
The WebSocket `call.status` read remains session-bounded to active calls and
the last 256 completed snapshots; use these GET helpers for durable history.

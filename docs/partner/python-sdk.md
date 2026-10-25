# Python SDK quickstart

```bash
# SDK 0.4.0: realtime + durable history
pip install asterisk-ai-agent-gateway-sdk==0.4.0
export GATEWAY_URL=https://gateway.example.com
export GATEWAY_API_KEY=agw_live_REDACTED
export GATEWAY_AGENT_SLUG=support-agent
python sdks/python/examples/echo_agent.py
```

The example reads `GATEWAY_AGENT_SLUG`; current sample readers retain
`AGENT_SLUG` as a compatibility fallback.

SDK 0.4.0 includes the realtime client and durable history helpers. For a
controlled rollout where the operator supplies a direct artifact, use it as a
secondary install option:

```bash
python -m pip install "https://gateway.example.com/downloads/sdk-0.4.0/asterisk_ai_agent_gateway_sdk-0.4.0-py3-none-any.whl"
```

Replace `gateway.example.com` with the artifact host supplied by the operator.

`GatewayClient.run(on_event=..., on_audio=...)` exchanges the key for a
five-minute token, registers the slug, heartbeats every 10 seconds, reconnects
with a fresh token, and decodes the 16-byte call UUID envelope. `on_audio`
receives `(call_id, pcm)` with mono PCM16 at the rate `call.started` announced;
pass synthesized audio back
through `send_audio(call_id, pcm)`.

Control helpers cover every scoped command — `hangup`, `hold`, `resume`,
`mute`, `unmute`, `send_dtmf`, `clear_audio`, `transfer_blind`,
`transfer_attended`, `transfer_cancel`, `route`, `originate`,
`cancel_outbound` — and each generates an idempotent `request_id`.

The connection flow retries authentication failures three times with a fresh
token before raising the final `AuthenticationError`. Direct `realtime_token()`
calls remain one-shot; `reconnect=False` disables automatic retries. See
[authentication](authentication.md#automatic-sdk-connection-retries) for the
shared retry budget and backoff. Never log the API key, ephemeral token, or
raw caller audio.

The gateway keeps the most recent registration per slug. When another process
registers the same slug, this client's calls are hung up, the socket closes
with `4409`, and `run()`/`stream()` raise `SessionSupersededError` without
reconnecting.

Use `GatewayClient.stream()` instead of `run()` when you want to pull events
and audio yourself as an async iterator.

## Durable call history

The async history helpers use the long-lived API key directly as
`Authorization: Bearer`; they require `calls:read`, do not exchange a
realtime token, and do not open a WebSocket. Each request is restricted to the
key's organization and partner app.

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
`total_pages >= 1` even for an empty result). Use timezone-qualified ISO 8601
values for date filters. Call summaries are newest first; signals are oldest
first by `sequence`. Numbered pages can shift when new calls arrive, so use
cursor mode for reliable iteration. The history surface stores metadata and
normalized status signals only, with no audio, transcripts, or phone numbers
and no automatic deletion. The WebSocket `call.status` read remains limited to
the active calls and last 256 completed snapshots in that session; use these
GET helpers for history that survives reconnects and restarts.

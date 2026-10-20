# AI Agent Gateway — Node SDK

SDK 0.4.0 client for realtime protocol v1 and durable call history. It
exchanges your API key for a five-minute token, registers the agent slug,
heartbeats, reconnects with a fresh token, and hides the 16-byte binary audio
envelope.

```bash
# Realtime + durable history
npm install asterisk-ai-agent-gateway-sdk@0.4.0
```

```js
import { GatewayClient } from "asterisk-ai-agent-gateway-sdk";

const client = new GatewayClient({
  gatewayUrl: process.env.GATEWAY_URL,
  apiKey: process.env.GATEWAY_API_KEY,   // keep in a secret store
  agentSlug: "support-agent",
});

client.on("call.started", (event) => console.log("call up", event.call_id));
client.on("audio", ({ callId, pcm }) => client.sendAudio(callId, pcm));

await client.start();
```

Run one client per `agentSlug`: the gateway keeps one live connection per
slug, and the most recent registration wins. A replaced client receives
close code `4409`, emits `SessionSupersededError` on `error`, and stops
without reconnecting; the gateway hangs up the calls it owned.

Every JSON event is emitted twice — once as `event`, once under its own type
(`call.started`, `dtmf.received`, `call.ended`, …). Binary frames arrive
decoded on `audio`.

`GatewayClient.start()` retries authentication failures three times after the
initial attempt (four attempts total). The shared budget covers token exchange
HTTP `401`/`403`, WebSocket handshake `401`/`403`, and close code `4401`. Each
retry exchanges the key for a fresh token after 1, 2, then 4 seconds, capped by
`maxBackoffMs`; the budget resets only after `session.ready`. Set
`reconnect: false` to disable retries; `close()` stops pending retries. If
authentication fails before `start()` resolves, the final
`AuthenticationError` rejects `start()`. If a later reconnect exhausts its
budget after `start()` resolved, `AuthenticationError` is emitted on `error`
and stops the client. A revoked key cannot be revived. Direct
`realtimeToken()` is a single request and does not retry itself. Other
transport failures reconnect with exponential backoff up to `maxBackoffMs`.
Authentication and transport failures share that backoff, so preceding
transport failures can increase the next authentication retry's delay.

See `examples/echo-agent.mjs` and `docs/partner/integration-guide.html`.

## Durable call history

SDK 0.4.0 includes the durable history GET helpers alongside the realtime
client. They use the long-lived API key directly as `Authorization: Bearer`;
they do not mint a realtime token, open a WebSocket, or depend on a live
session. The key needs the `calls:read` scope and is restricted to its
organization and partner app.

For a controlled rollout where the operator supplies a direct artifact, use it
as a secondary install option:

```bash
npm install "https://gateway.example.com/downloads/sdk-0.4.0/asterisk-ai-agent-gateway-sdk-0.4.0.tgz"
```

Replace `gateway.example.com` with the artifact host supplied by the operator.

```js
const page = await client.listCalls({
  limit: 50,                         // 1..100; default 50
  cursor: nextCursor,                // omit on the first page
  agentSlug: "support-agent",        // exact historic slug; omit for all
  status: "completed",
  direction: "outbound",
  startedAfter: "2026-10-20T00:00:00Z",
  startedBefore: "2026-10-21T00:00:00Z",
});

const call = await client.getCall(callId);
const signals = await client.listCallSignals(callId, {
  limit: 50,                         // 1..100; default 50
  cursor: signalCursor,
});

// Numbered mode alternative: omit cursor and pass a positive page number.
const numbered = await client.listCalls({ agentSlug: "support-agent", page: 1 });
```

`listCalls()` returns `{ items, next_cursor, page, page_size, total,
total_pages }`; the four numbered metadata fields are `null` in cursor mode.
`getCall()` returns one call summary, and `listCallSignals()` returns its
`items` plus `next_cursor`. Node uses camelCase `agentSlug`, `startedAfter`,
and `startedBefore`; the REST spellings `agent_slug`, `started_after`, and
`started_before` are also accepted when mirroring query parameters. Pass a
positive integer `page` to use numbered pagination instead of `cursor`; the
Gateway rejects both together with `422`, returns `next_cursor: null` in page
mode, and reports `page_size`, `total`, and `total_pages` (with
`total_pages >= 1` even for an empty result). Timestamps must include an ISO
8601 timezone. Call summaries are newest first; signals are oldest first by
`sequence`. Numbered pages can shift when new calls arrive, so use cursor mode
for reliable iteration.

History contains metadata and normalized status signals only. It does not store
audio, transcripts, or phone numbers, and records have no automatic deletion.
The WebSocket `call.status` read remains session-bounded to active calls and
the last 256 completed snapshots; use these GET helpers for durable history.

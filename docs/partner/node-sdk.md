# Node SDK quickstart

```bash
# SDK 0.4.0: realtime + durable history
npm install asterisk-ai-agent-gateway-sdk@0.4.0
export GATEWAY_URL=https://gateway.example.com
export GATEWAY_API_KEY=agw_live_REDACTED
export GATEWAY_AGENT_SLUG=support-agent
node sdks/node/examples/echo-agent.mjs
```

The example reads `GATEWAY_AGENT_SLUG` first and retains `AGENT_SLUG` as a
compatibility fallback.

SDK 0.4.0 includes the realtime client and durable history helpers. For a
controlled rollout where the operator supplies a direct artifact, use it as a
secondary install option:

```bash
npm install "https://gateway.example.com/downloads/sdk-0.4.0/asterisk-ai-agent-gateway-sdk-0.4.0.tgz"
```

Replace `gateway.example.com` with the artifact host supplied by the operator.

```js
import { GatewayClient } from "asterisk-ai-agent-gateway-sdk";

const client = new GatewayClient({
  gatewayUrl: process.env.GATEWAY_URL,
  apiKey: process.env.GATEWAY_API_KEY,
  agentSlug: process.env.GATEWAY_AGENT_SLUG ?? process.env.AGENT_SLUG ?? "support-agent",
});

client.on("call.started", (event) => console.log("call up", event.call_id));
client.on("audio", ({ callId, pcm }) => client.sendAudio(callId, pcm));

await client.start();
```

The client exchanges the long-lived key for a five-minute token, registers the
agent, heartbeats every 10 seconds, reconnects with a fresh token, and hides
the binary call UUID envelope. Every JSON event is emitted twice: once as
`event`, once under its own type. Binary frames arrive decoded on `audio` as
`{ callId, pcm }`.

Control helpers mirror the Python SDK — `hangup`, `hold`, `resume`, `mute`,
`unmute`, `sendDtmf`, `clearAudio`, `transferBlind`, `transferAttended`,
`transferCancel`, `route`, `originate`, `cancelOutbound` — each returning the
idempotent `requestId` it generated.

The connection flow retries authentication failures three times with a fresh
token. Exhaustion before the first socket opens rejects `start()` with
`AuthenticationError`; after opening, the final failure is emitted on `error`.
Direct `realtimeToken()` calls remain one-shot; `reconnect: false` disables
automatic retries. See [authentication](authentication.md#automatic-sdk-connection-retries)
for the shared retry budget and backoff. Requires Node 18.17 or newer.
TypeScript declarations ship in `types/index.d.ts`.

The gateway keeps the most recent registration per slug. When another process
registers the same slug, this client's calls are hung up, the socket closes
with `4409`, and the client emits `SessionSupersededError` on `error` and stops
without reconnecting.

## Durable call history

The history helpers use the long-lived API key directly as
`Authorization: Bearer`; they require `calls:read`, do not exchange a
realtime token, and do not open a WebSocket. Each request is restricted to the
key's organization and partner app.

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
`total_pages >= 1` even for an empty result). Use timezone-qualified ISO 8601
values for the date filters. Call summaries are newest first; signals are
oldest first by `sequence`. Numbered pages can shift when new calls arrive, so
use cursor mode for reliable iteration. The history surface stores metadata
and normalized status signals only, with no audio, transcripts, or phone
numbers and no automatic deletion. The WebSocket `call.status` read remains
limited to the active calls and last 256 completed snapshots in that session;
use these GET helpers for history that survives reconnects and restarts.

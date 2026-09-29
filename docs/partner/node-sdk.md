# Node SDK quickstart

```bash
npm install asterisk-ai-agent-gateway-sdk
export GATEWAY_URL=https://gateway.example.com
export GATEWAY_API_KEY=agw_live_REDACTED
export AGENT_SLUG=support-agent
node sdks/node/examples/echo-agent.mjs
```

```js
import { GatewayClient } from "asterisk-ai-agent-gateway-sdk";

const client = new GatewayClient({
  gatewayUrl: process.env.GATEWAY_URL,
  apiKey: process.env.GATEWAY_API_KEY,
  agentSlug: "support-agent",
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

# Node SDK quickstart

```bash
npm install ./sdks/node
export GATEWAY_URL=https://gateway.example.com
export GATEWAY_API_KEY=agw_live_REDACTED
export AGENT_SLUG=support-agent
node sdks/node/examples/echo-agent.mjs
```

```js
import { GatewayClient } from "@asterisk-ai-agent-gateway/sdk";

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

An `AuthenticationError` on the `error` channel stops the client and must not
be retried. Requires Node 18.17 or newer. TypeScript declarations ship in
`types/index.d.ts`.

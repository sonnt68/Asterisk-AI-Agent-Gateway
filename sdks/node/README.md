# Asterisk AI Agent Gateway — Node SDK

Realtime protocol v1 client. Exchanges your API key for a five-minute token,
registers the agent slug, heartbeats, reconnects with a fresh token, and hides
the 16-byte binary audio envelope.

```bash
npm install asterisk-ai-agent-gateway-sdk
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

Run one client per `agentSlug`: the gateway accepts a single live connection
per slug and answers a second one with `agent-in-use`.

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

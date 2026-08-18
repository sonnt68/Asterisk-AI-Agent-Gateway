# Asterisk AI Agent Gateway — Node SDK

Realtime protocol v1 client. Exchanges your API key for a five-minute token,
registers the agent slug, heartbeats, reconnects with a fresh token, and hides
the 16-byte binary audio envelope.

```bash
npm install ./sdks/node
```

```js
import { GatewayClient } from "@asterisk-ai-agent-gateway/sdk";

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

An `AuthenticationError` on the `error` channel stops the client and is never
retried: the key is revoked, expired, or its partner app is disabled. Every
other transport failure reconnects with exponential backoff.

See `examples/echo-agent.mjs` and `docs/partner/integration-guide.html`.

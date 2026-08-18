// Echo agent: proves both media directions in about thirty lines.
//
//   export GATEWAY_URL=https://gateway.example.com
//   export GATEWAY_API_KEY=agw_live_...
//   export AGENT_SLUG=support-agent
//   node examples/echo-agent.mjs
//
// Every frame the caller speaks is sent straight back, so hearing yourself
// means audio flows partner -> gateway -> Asterisk and back.

import { GatewayClient } from "../src/index.js";

const client = new GatewayClient({
  gatewayUrl: process.env.GATEWAY_URL,
  apiKey: process.env.GATEWAY_API_KEY,
  agentSlug: process.env.AGENT_SLUG ?? "support-agent",
});

client.on("session.ready", () => console.log("registered as", client.connectionId));
client.on("call.started", (event) => console.log("call up", event.call_id, event.caller));
client.on("dtmf.received", (event) => console.log("dtmf", event.digit, "on", event.call_id));
client.on("call.ended", (event) => console.log("call down", event.call_id));
client.on("error", (event) => console.error("gateway error", event.code ?? "", event.message ?? event));
client.on("reconnecting", ({ delayMs }) => console.warn(`reconnecting in ${delayMs}ms`));

client.on("audio", ({ callId, pcm }) => client.sendAudio(callId, pcm));

await client.start();

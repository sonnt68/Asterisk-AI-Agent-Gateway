/**
 * A complete gateway agent, in as few lines as the protocol allows.
 *
 * It echoes the caller back to themselves, which proves both audio directions
 * without needing a model. Replace the `audio` handler with your own pipeline.
 *
 *   npm install asterisk-ai-agent-gateway-sdk
 *   export GATEWAY_URL=https://gateway.example.com
 *   export GATEWAY_API_KEY=...        # from a secret store, not a file
 *   node echo-agent.mjs
 */

import { GatewayClient } from "asterisk-ai-agent-gateway-sdk";

const client = new GatewayClient({
  gatewayUrl: process.env.GATEWAY_URL,
  apiKey: process.env.GATEWAY_API_KEY,
  agentSlug: "support-agent",
});

// The rate is announced per call, so it belongs to the call, not to the module.
// A model that emits a fixed rate resamples against this number — and wants an
// integer ratio when it does. See references/audio.md.
const rates = new Map();

client.on("call.started", (event) => {
  rates.set(event.call_id, event.media.sample_rate);
  console.log("call up", event.call_id, "at", event.media.sample_rate, "Hz");
});

client.on("call.ended", (event) => {
  // Release everything call-local here, or the next call inherits it.
  rates.delete(event.call_id);
  console.log("call down", event.call_id);
});

client.on("error", (error) => console.error("gateway refused:", error.message));

// Mono PCM s16le at rates.get(callId). Send audio back the same way.
client.on("audio", ({ callId, pcm }) => client.sendAudio(callId, pcm));

await client.start();

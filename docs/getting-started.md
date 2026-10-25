# First partner call

The Gateway operator provides the Gateway URL, agent slug, API key, allowed
destinations and any required routing identifiers. The plaintext key is shown
once; store it in a secret manager.

Choose one SDK:

```bash
pip install asterisk-ai-agent-gateway-sdk
export GATEWAY_URL=https://gateway.example.com
export GATEWAY_API_KEY=agw_live_REDACTED
export GATEWAY_AGENT_SLUG=support-agent
python sdks/python/examples/echo_agent.py
```

The sample reads `GATEWAY_AGENT_SLUG` first and accepts `AGENT_SLUG` as a
compatibility fallback.

Node instead:

```bash
npm install asterisk-ai-agent-gateway-sdk
node sdks/node/examples/echo-agent.mjs
```

The SDK exchanges the key for a five-minute token, opens one outbound WSS
connection and registers the slug. Ask the Gateway operator to route an
approved test call to that agent.

A successful call produces `call.started`, binary mono PCM16 frames at the
rate that event announced, and
`call.ended`. Echoing each binary frame proves both media directions. All
integration traffic uses the documented Gateway endpoints.

Both SDKs already handle heartbeats, reconnect with a fresh token, and the
binary audio envelope. Before production, add bounded model queues, call
timeouts, structured errors, key rotation and a human fallback destination.

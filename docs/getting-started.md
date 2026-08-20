# First partner call

An operator first connects the single Asterisk per
[`operations/asterisk-connection.md`](operations/asterisk-connection.md), creates
a partner app in the dashboard and issues an API key. The plaintext key is
shown once; store it in a secret manager.

Choose one SDK:

```bash
pip install asterisk-ai-agent-gateway-sdk
export GATEWAY_URL=https://gateway.example.com
export GATEWAY_API_KEY=agw_live_REDACTED
export AGENT_SLUG=support-agent
python sdks/python/examples/echo_agent.py
```

Node instead:

```bash
npm install asterisk-ai-agent-gateway-sdk
node sdks/node/examples/echo-agent.mjs
```

The SDK exchanges the key for a five-minute token, opens one outbound WSS
connection and registers the slug. Route the extension to:

```asterisk
Set(AI_GATEWAY_AGENT=support-agent)
Stasis(asterisk-ai-gateway)
```

A successful call produces `call.started`, binary mono PCM16 frames at the
rate that event announced, and
`call.ended`. Echoing each binary frame proves both media directions. Partners
never configure ARI, SIP, AudioSocket or RTP.

Both SDKs already handle heartbeats, reconnect with a fresh token, and the
binary audio envelope. Before production, add bounded model queues, call
timeouts, structured errors, key rotation and a human fallback destination.

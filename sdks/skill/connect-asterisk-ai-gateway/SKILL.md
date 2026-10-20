---
name: connect-asterisk-ai-gateway
description: Connect an AI voice agent through AI Agent Gateway. Use when building, debugging, or reviewing a partner integration that needs API-key token exchange, realtime WebSocket events, PCM audio framing, or scoped call-control commands.
---

# Connect an AI agent through Gateway

You reach Gateway through three documented public surfaces: one REST call that
turns your API key into a short-lived token, direct REST GETs for durable call
history, and one WebSocket that carries call events, audio, and control
commands. If a task seems to need access outside the documented Gateway
endpoints, it is either solvable through these surfaces or it is a request for
the Gateway operator — not something to work around.

## Start here

Install a published SDK rather than framing the protocol by hand. Both
packages share one name and version, and both handle the token exchange,
registration, heartbeat, reconnect-with-fresh-token, and the binary audio
envelope:

```bash
pip install asterisk-ai-agent-gateway-sdk==0.3.2  # Python 3.10+
npm  install asterisk-ai-agent-gateway-sdk@0.3.2 # Node 18.17+
```

`examples/echo_agent.py` and `examples/echo-agent.mjs` are complete working
agents — start from one and replace the audio handler with your model.
`examples/dial_out.py` adds the outbound case, where the destination is yours
to choose and the allowlist is felt.

The current published SDK `0.3.2` handles the realtime surface. The history
helpers below require the operator-provided `0.4.0` build (such as a local
wheel or tarball) until publication is confirmed; do not assume a registry
install already contains them.

Use the operator's supplied host for direct artifacts when needed:

```bash
python -m pip install "https://gateway.example.com/downloads/sdk-0.4.0/asterisk_ai_agent_gateway_sdk-0.4.0-py3-none-any.whl"
npm install "https://gateway.example.com/downloads/sdk-0.4.0/asterisk-ai-agent-gateway-sdk-0.4.0.tgz"
```

Raw framing is documented in `references/protocol.md` for clients that cannot
use either SDK. Reach for it only then; hand-rolled framing is where
integrations break.

The SDKs also expose `GatewayClient.listCalls()` / `list_calls()`,
`getCall()` / `get_call()`, and `listCallSignals()` / `list_call_signals()` for
durable history. These helpers use the long-lived API key directly with
`calls:read`; they do not exchange a realtime token or open a WebSocket. The
list helpers accept an exact historic `agentSlug` / `agent_slug` filter and an
optional positive `page` number. `page` activates numbered mode while `cursor`
activates cursor mode; sending both returns `422`. Cursor mode keeps numbered
metadata null and is recommended when new calls may arrive, because numbered
pages can shift.

## The four things integrations get wrong

**1. The audio sample rate is announced per call, not fixed.** Read
`media.sample_rate` from `call.started` and use it for that call in both
directions. Hardcoding a rate is the single most common cause of "the audio
sounds bad but nothing errors" — see `references/audio.md`, which explains why
a wrong-but-plausible rate degrades quality silently instead of failing.

**2. One connection per `agent_slug`, and the newest wins.** A new
registration closes the old connection with `4409` and hangs up its calls; the
SDKs raise `SessionSupersededError` and do not reconnect. Deploys must drain
in-flight calls before the new process registers, and two environments need
two slugs.

**3. Connection authentication has a bounded retry budget.** Python
`run()`/`stream()` and Node `start()` retry auth failures three times after the
initial attempt (four attempts total). The shared budget covers token HTTP
`401`/`403`, WebSocket handshake `401`/`403`, and close `4401`. Each retry
mints a *new* token after 1, 2, then 4 seconds, capped by `max_backoff` or
`maxBackoffMs`; the budget resets only when `session.ready` arrives.
`reconnect=False`/`false` disables retries, and `close()` stops pending ones.
Python task cancellation also stops them. After the budget, Python raises
`AuthenticationError`; Node's initial `start()` rejects, while a later
reconnect emits it on `error` and stops the client. Retries cannot revive a
revoked key. Direct `realtime_token()`/`realtimeToken()` helpers make one
request and do not retry themselves. Other transport failures reconnect with
backoff. Both failure types share the backoff, so preceding transport failures
can increase the next authentication retry's delay up to the configured cap.

**4. Every command needs its scope, and destinations need the allowlist.**
Check `references/call-control.md` before adding a command. A command your key
lacks scope for is rejected by Gateway before execution, so the failure
arrives as `command-denied` rather than as a broken call.

For an outbound call, the `context:extension` must be allowlisted and the
`context` must be the outbound routing identifier supplied by the Gateway
operator. Ask the operator to confirm both; do not infer the outbound route
from an incoming call's settings.

## Working rules

- Keep one handler chain and one buffer per gateway `call_id`. Release both on
  `call.ended`.
- Correlate every event and control on the gateway-issued `call_id`.
- Put the API key in a secret store. Never in a URL, a log line, an error
  message, a config file under version control, or a prompt.
- Send retried control commands with the same UUID `request_id`. The
  connection remembers accepted results, so a retry cannot fire the same
  call-control action twice.
- Use the direct GET history helpers for durable reads. `call.status` on the
  WebSocket remains session-bounded to active calls and the last 256 completed
  snapshots.
- Do not prepend bytes to audio the SDK sends. The envelope is exactly the 16
  raw UUID bytes and nothing else.

## References

Read the one that matches the task; they are written to be read on demand.

| File | Read it when |
|---|---|
| `references/protocol.md` | framing by hand, or debugging the wire |
| `references/audio.md` | audio quality is wrong, or choosing a rate |
| `references/authentication.md` | keys, tokens, rotation, rate limits |
| `references/call-control.md` | adding a command, transfer, or outbound call |
| `references/troubleshooting.md` | the gateway sent an error code |

---
name: connect-asterisk-ai-gateway
description: Connect an AI voice agent to an Asterisk PBX through the Asterisk AI Agent Gateway. Use when building, debugging, or reviewing a partner integration that needs API-key token exchange, the realtime WebSocket protocol, PCM audio framing, or scoped call-control commands — without ARI, SIP, or AudioSocket credentials.
---

# Connect an AI agent to Asterisk through the gateway

You reach the PBX through exactly two surfaces: one REST call that turns your
API key into a short-lived token, and one WebSocket that carries call events,
audio, and control commands. There is no third surface. If a task seems to
need ARI, SIP, AudioSocket, RTP, or host access, it is either solvable through
these two or it is a request for the gateway operator — not something to work
around.

## Start here

Install a published SDK rather than framing the protocol by hand. Both
packages share one name and version, and both handle the token exchange,
registration, heartbeat, reconnect-with-fresh-token, and the binary audio
envelope:

```bash
pip install asterisk-ai-agent-gateway-sdk      # Python 3.10+
npm  install asterisk-ai-agent-gateway-sdk     # Node 18.17+
```

`examples/echo_agent.py` and `examples/echo-agent.mjs` are complete working
agents — start from one and replace the audio handler with your model.

Raw framing is documented in `references/protocol.md` for clients that cannot
use either SDK. Reach for it only then; hand-rolled framing is where
integrations break.

## The four things integrations get wrong

**1. The audio sample rate is announced per call, not fixed.** Read
`media.sample_rate` from `call.started` and use it for that call in both
directions. Hardcoding a rate is the single most common cause of "the audio
sounds bad but nothing errors" — see `references/audio.md`, which explains why
a wrong-but-plausible rate degrades quality silently instead of failing.

**2. One connection per `agent_slug`.** A second one is refused with
`agent-in-use`. Deploys must drain in-flight calls before the old process
exits, or the new one cannot register.

**3. `AuthenticationError` is terminal; everything else retries.** A rejected
key will not start working on retry — it is revoked, expired, or its partner
app is disabled. Transport failures reconnect with backoff, and each reconnect
mints a *new* token; tokens live five minutes and are never replayed.

**4. Every command needs its scope, and destinations need the allowlist.**
Check `references/call-control.md` before adding a command. A command your key
lacks scope for is rejected before Asterisk is ever called, so the failure
arrives as `command-denied` rather than as a broken call.

## Working rules

- Keep one handler chain and one buffer per gateway `call_id`. Release both on
  `call.ended`.
- Correlate on the gateway's `call_id`. Asterisk channel IDs are not exposed
  and must never appear in your data model.
- Put the API key in a secret store. Never in a URL, a log line, an error
  message, a config file under version control, or a prompt.
- Send retried control commands with the same UUID `request_id`. The
  connection remembers accepted results, so a retry cannot fire the same
  Asterisk action twice.
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

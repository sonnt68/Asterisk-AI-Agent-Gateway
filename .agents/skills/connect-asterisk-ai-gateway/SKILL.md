---
name: connect-asterisk-ai-gateway
description: Connect a third-party AI agent to Asterisk through Asterisk AI Agent Gateway. Use when implementing, debugging, or documenting a partner AI integration that needs API-key token exchange, Gateway SDKs, realtime WebSocket events, PCM16 audio, or scoped call-control commands without ARI/SIP credentials.
---

# Connect Asterisk AI Gateway

Use public REST and realtime surfaces only. Keep Asterisk, AudioSocket, RTP,
ARI credentials, and raw media transports inside the gateway boundary.

## Workflow

1. Read `references/realtime-protocol.md` before changing an integration.
2. Obtain a partner API key through the dashboard; never print or commit it.
3. Prefer `sdks/python` or `sdks/node`; they exchange the key, register,
   heartbeat, reconnect, and frame audio.
4. Keep one handler/buffer chain per gateway `call_id`. Audio is PCM signed
   16-bit little-endian mono 16 kHz.
5. Send only commands whose granted scope permits them.
6. Validate against the local gateway before deployment.

## Guardrails

- Do not request or expose ARI, SIP, AudioSocket, RTP, Docker, or host access.
- Keep API keys in secret storage and redact them from logs/errors.
- Use the gateway-issued `call_id`, never an Asterisk channel ID, for partner
  authorization or correlation.
- Obtain a new token on reconnect; never replay an expired token.
- Never prepend custom bytes to SDK audio; raw framing is only for clients that
  cannot use an SDK.

Read `references/realtime-protocol.md` for v1 event/audio/control details.

# Python SDK quickstart

```bash
pip install asterisk-ai-agent-gateway-sdk
export GATEWAY_URL=https://gateway.example.com
export GATEWAY_API_KEY=agw_live_REDACTED
export AGENT_SLUG=support-agent
python sdks/python/examples/echo_agent.py
```

`GatewayClient.run(on_event=..., on_audio=...)` exchanges the key for a
five-minute token, registers the slug, heartbeats every 10 seconds, reconnects
with a fresh token, and decodes the 16-byte call UUID envelope. `on_audio`
receives `(call_id, pcm)` with mono PCM16 at the rate `call.started` announced;
pass synthesized audio back
through `send_audio(call_id, pcm)`.

Control helpers cover every scoped command — `hangup`, `hold`, `resume`,
`mute`, `unmute`, `send_dtmf`, `clear_audio`, `transfer_blind`,
`transfer_attended`, `transfer_cancel`, `route`, `originate`,
`cancel_outbound` — and each generates an idempotent `request_id`.

`AuthenticationError` ends the stream and must not be retried: the key is
revoked, expired, or its partner app is disabled. Never log the API key, the
ephemeral token, or raw caller audio.

Use `GatewayClient.stream()` instead of `run()` when you want to pull events
and audio yourself as an async iterator.

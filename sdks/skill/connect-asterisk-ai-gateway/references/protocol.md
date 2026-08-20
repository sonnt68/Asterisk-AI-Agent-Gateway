# Realtime protocol v1

## Opening a session

1. `POST /api/v1/realtime/tokens` with `Authorization: Bearer <api-key>`.
   The response token is valid for five minutes and is only ever used for the
   handshake.
2. Connect to `wss://<gateway>/v1/realtime?token=<token>`.
3. Send the registration frame first — nothing else is accepted before it:

```json
{"type": "session.register", "agent_slug": "support-agent", "protocol_version": "1"}
```

The gateway answers `session.ready`. Heartbeat every 10 seconds; the lease in
Redis expires after 30. A second connection for the same `agent_slug` is
refused with `agent-in-use`.

## Text frames

JSON, one object per frame.

| Event | Meaning |
|---|---|
| `session.ready` | registration accepted; you may send audio |
| `call.started` | a call is up — carries `call_id`, `agent_slug`, `caller`, and `media` |
| `call.ended` | release everything held for that `call_id` |
| `dtmf.received` | the caller pressed a key |
| `transfer.consulting` | an attended-transfer consult leg is live |
| `call.control.accepted` | a command succeeded; may carry a `result` |
| `error` | carries `code` and `message` — see `troubleshooting.md` |

`call.started` announces the media format for that call:

```json
{
  "type": "call.started",
  "call_id": "8c1f4b2e-0d5a-4f77-9a51-6b0c7e2d3a44",
  "sequence": 1,
  "agent_slug": "support-agent",
  "media": {"encoding": "pcm_s16le", "sample_rate": 8000, "channels": 1},
  "caller": {"name": "…", "number": "…"}
}
```

Read `media` rather than assuming it. `encoding` is `pcm_s16le` on the normal
transport and `pcm_mulaw` on the external-media fallback, and `sample_rate`
depends on the deployment. `references/audio.md` explains why this matters.

## Binary frames

```text
bytes 0..15   the call_id as 16 raw RFC 4122 bytes, not its 36-char string
bytes 16..N   raw audio in the format call.started announced
```

The same layout in both directions. The SDKs add and strip it for you.

A frame is rejected when:

- it arrives before `session.register` succeeded → `protocol-invalid`
- it is 16 bytes or shorter, i.e. a UUID with no audio → `audio-invalid`
- the `call_id` is not an active call on this connection → `call-not-active`
- the Asterisk-side media path is not ready yet → `media-unavailable`

Partner-bound audio sits in a bounded 100-frame queue. A consumer that stalls
loses its oldest frames — deliberately, so that live audio stays live — and a
metric records it. If you are dropping frames, the fix is to consume faster,
not to buffer more.

## Shutdown

Disconnecting terminates the calls that connection owns. Revoking the key
blocks new tokens and new sessions but does not cut a call already in
progress.

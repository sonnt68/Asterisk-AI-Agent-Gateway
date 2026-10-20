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
Gateway expires after 30. The most recent registration for an `agent_slug`
wins: the older connection receives `session-superseded`, its calls are hung
up, and it is closed with `4409`. A superseded client must not reconnect.

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
- the call's media path is not ready yet → `media-unavailable`

Partner-bound audio sits in a bounded 100-frame queue. A consumer that stalls
loses its oldest frames — deliberately, so that live audio stays live — and a
metric records it. If you are dropping frames, the fix is to consume faster,
not to buffer more.

## Shutdown

Disconnecting terminates the calls that connection owns. Revoking the key
blocks new tokens and new sessions but does not cut a call already in
progress.

## Durable call history

Durable history is a separate HTTPS read surface. Send the long-lived API key
directly as `Authorization: Bearer`; do not exchange a realtime token and do
not open a WebSocket for these requests. The key needs `calls:read`, and every
request is restricted to both its organization and partner app.

```text
GET /api/v1/partner/calls
GET /api/v1/partner/calls/<call_id>
GET /api/v1/partner/calls/<call_id>/signals
```

The list endpoint accepts `limit` from `1` through `100` (default `50`),
`cursor`, exact historic `agent_slug`, `status`, `direction`, and
timezone-qualified ISO 8601 `started_after` / `started_before` filters. A
positive `page` selects numbered pagination; `page` and `cursor` are mutually
exclusive and return `422` when combined. Cursor mode returns the existing
`items` + `next_cursor` envelope with `page`, `page_size`, `total`, and
`total_pages` all null. Numbered mode returns those four metadata fields as
integers, sets `next_cursor` to null, and reports `total_pages` of at least `1`
even for an empty result. New calls can shift numbered pages, so use cursors
for iteration. The list and signal endpoints return `items` and
`next_cursor`; signals accept `limit` and `cursor` and are ordered by ascending
`sequence`.
Use the SDK history helpers when possible. History stores metadata and
normalized status signals only; it has no audio, transcripts, or phone numbers,
and has no automatic deletion. Legacy summaries without partner-app ownership
are not visible through partner endpoints.

SDK `0.4.0` provides these helper methods alongside the realtime client. Use
the pinned package install in the skill's “Start here” section. If the Gateway
operator supplies a direct artifact for a controlled rollout, that artifact is
a secondary install option.

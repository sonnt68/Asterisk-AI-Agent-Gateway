# Realtime protocol v1

Request a token with `POST /api/v1/realtime/tokens`, then connect to
`wss://<gateway>/v1/realtime?token=<token>`. The first frame must be:

```json
{"type":"session.register","agent_slug":"support-agent","protocol_version":"1"}
```

Text frames are JSON. Binary frames contain exactly:

```text
bytes 0..15   RFC 4122 gateway call UUID
bytes 16..N   PCM signed 16-bit little-endian, mono
```

The rate is not part of the framing. The gateway announces it per call in
`call.started`'s `media` block — 8000 Hz on a telephony deployment, higher
where both ends are genuinely wideband. Read it rather than assuming one: an
assumed rate costs a resample on each side of the wire, and a non-integer
ratio (24 kHz to 16 kHz, say) makes most anti-alias filters fall back to
linear interpolation without saying so.

The same framing is used in both directions. SDKs add/remove this envelope.
Asterisk channel IDs and AudioSocket details stay internal to the gateway.

Start call-local processing on `call.started`; release it on `call.ended`.
Heartbeat every 10 seconds. The Redis lease expires after 30 seconds. A second
connection for the same globally unique `agent_slug` is rejected.

Partner-bound audio uses a bounded 100-frame queue. If a consumer stalls, the
oldest frame is dropped and a metric is incremented so live audio stays current.
Retryable controls and outbound originate should include a UUID `request_id`;
the gateway remembers the latest 256 accepted results per connection.

Partner disconnect terminates owned calls safely. API-key revocation blocks new
tokens and WSS sessions; it does not forcibly kill an already connected call.
Errors contain a stable `code` and safe message, never credentials or raw audio.

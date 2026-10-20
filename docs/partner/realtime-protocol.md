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
Use the gateway-issued `call_id` to correlate every event, audio frame and control.

Start call-local processing on `call.started`; release it on `call.ended`.
Heartbeat every 10 seconds; the session lease expires after 30 seconds. The
newest connection for an `agent_slug` replaces the previous one, which closes
with `4409` and must not reconnect. Calls owned by the replaced connection end.

Partner-bound audio uses a bounded 100-frame queue. If a consumer stalls, the
oldest frame is dropped and a metric is incremented so live audio stays current.
Retryable controls and outbound originate should include a UUID `request_id`;
the gateway remembers the latest 256 accepted results per connection.

Partner disconnect terminates owned calls safely. API-key revocation blocks new
tokens and WSS sessions; it does not forcibly kill an already connected call.
Errors contain a stable `code` and safe message, never credentials or raw audio.

## Call progress and checking a result

The gateway emits additive `call.status` events for outbound progress and
normalized terminal results. Existing SDK event handlers receive them without
a package upgrade.

| Status | Meaning |
|---|---|
| `dialing` | Gateway accepted the outbound request; nobody has answered yet |
| `ringing` | The destination is reported as ringing |
| `answered` | The remote leg answered; wait for `call.started` before media/control |
| `completed` | An answered call ended |
| `busy` | Destination busy |
| `no_answer` | Explicit no-answer result or elapsed originate timeout |
| `rejected` | Call rejected by the destination or calling service |
| `unavailable` | Destination unavailable or no route |
| `failed` | Call setup/media failure or an unknown premature termination |
| `cancelled` | Call cancelled before answer |

The last seven statuses are terminal. `call.ended` follows cleanup and includes
all snapshot fields below, so every accepted call can finish even without a
`call.started`. `answered: true` distinguishes a real answer from an attempted
call. `sequence` increases on status transitions; queries return the current
sequence, and `updated_at` is a UTC timestamp. These sequence numbers belong to
status snapshots; the legacy `call.started.sequence` remains independent.
`hangup_cause` is the numeric termination cause when available; `dial_status`
is the observed dialing result. Use `status` for the normalized outcome.

An unknown cause is not automatically no-answer. An outbound timeout can
report cause `0`; the gateway reports `no_answer` only
when the known dialing deadline elapsed. A failure before that remains
`failed`. Different handset actions may produce the same reported cause;
the normalized result reflects the call signals available to Gateway.

To check a call, send this through the same registered WebSocket. The key needs
`calls:read`; `request_id` is optional, but include a UUID when you need to
correlate the reply:

```json
{"type":"call.control","command":"call.status","call_id":"<gateway-call-uuid>","request_id":"<new-request-uuid>"}
```

The response is always a fresh snapshot. If the query includes `request_id`,
the response echoes it:

```json
{"type":"call.status","call_id":"<gateway-call-uuid>","status":"no_answer","terminal":true,"answered":false,"reason":"timeout","hangup_cause":0,"dial_status":"RINGING","sequence":3,"updated_at":"2026-10-20T01:00:00+00:00","request_id":"<new-request-uuid>"}
```

Use the existing SDK's generic control method:

```python
await client.control(call_id, "call.status")
# Read the matching call.status in your event handler / stream.
```

```javascript
client.on("call.status", event => console.log(event.call_id, event.status));
client.control(callId, "call.status");
```

Active calls and the last 256 completed results are available only within their
owning WebSocket connection. Reconnect, restart, eviction, or another connection
cannot retrieve them; unknown and non-owned IDs receive the same generic
`command-failed` error. Retrying a status query reads the latest state even
if its request ID is reused.

## Durable call history through GET

Durable history is a separate HTTPS read surface. Send the long-lived API key
directly as `Authorization: Bearer`; do not exchange a realtime token and do
not open a WebSocket for these reads. The key must be active, enabled,
unexpired, unrevoked, and carry `calls:read`.

Every partner-history request is restricted to both the key's organization and
its partner app. Unknown, foreign, and non-owned call IDs return the same
generic `404`, so a caller cannot use this API to discover another app's
records.

### List calls

```http
GET /api/v1/partner/calls
Authorization: Bearer agw_live_<prefix>_<secret>
```

Query parameters are optional. `limit` accepts `1` through `100` and defaults
to `50`; `cursor` is the opaque value returned by the preceding page;
`agent_slug` is an exact historic agent-slug filter; `status` accepts the
normalized statuses above; `direction` accepts `inbound`, `outbound`, or
`unknown`; and `started_after` / `started_before` accept ISO 8601 timestamps
with an explicit timezone. Results are newest first by `created_at`, with
`call_id` as the stable tie-breaker.

Omit `page` to use cursor pagination. Supplying `page` as an integer greater
than or equal to `1` activates numbered pagination while keeping the same
`limit` default and maximum. `page` and `cursor` are mutually exclusive; a
request containing both returns `422`. Cursor pagination is recommended for
iterating a changing history because numbered pages can shift when new calls
arrive.

The response always has this envelope:

```json
{
  "items": [
    {
      "call_id": "8c1f4b2e-0d5a-4f77-9a51-6b0c7e2d3a44",
      "partner_app_id": "…",
      "agent_slug": "support-agent",
      "direction": "outbound",
      "source": "gateway",
      "status": "completed",
      "terminal": true,
      "answered": true,
      "reason": "normal_hangup",
      "hangup_cause": 16,
      "dial_status": "ANSWER",
      "sequence": 3,
      "created_at": "2026-10-20T01:00:00+00:00",
      "updated_at": "2026-10-20T01:02:03+00:00",
      "answered_at": "2026-10-20T01:00:05+00:00",
      "ended_at": "2026-10-20T01:02:03+00:00",
      "duration_seconds": 123,
      "talk_seconds": 118,
      "history_complete": true
    }
  ],
  "next_cursor": null,
  "page": null,
  "page_size": null,
  "total": null,
  "total_pages": null
}
```

In numbered mode, `page` is the requested page, `page_size` is the effective
limit, `total` is the filtered count, and `total_pages` is the computed page
count. `next_cursor` is `null` in that mode, and `total_pages` is at least `1`
even when the filtered result is empty. Cursor mode keeps the four numbered
metadata fields `null` and preserves the existing `next_cursor` behavior.

For example, this request reads page two for one historic agent:

```http
GET /api/v1/partner/calls?agent_slug=support-agent&limit=50&page=2
Authorization: Bearer agw_live_<prefix>_<secret>
```

`GET /api/v1/partner/calls/{call_id}` returns one item with the same shape.
`GET /api/v1/partner/calls/{call_id}/signals` returns the normalized
`call.status` snapshots for that call. Signals are ordered oldest first by
`sequence` and accept the same `limit` and `cursor` pagination shape:

```json
{
  "items": [
    {
      "type": "call.status",
      "call_id": "8c1f4b2e-0d5a-4f77-9a51-6b0c7e2d3a44",
      "status": "completed",
      "sequence": 3,
      "terminal": true,
      "answered": true,
      "reason": "normal_hangup",
      "hangup_cause": 16,
      "dial_status": "ANSWER",
      "updated_at": "2026-10-20T01:02:03+00:00"
    }
  ],
  "next_cursor": null
}
```

Gateway retains call metadata and normalized status signals indefinitely; there
is no automatic deletion. It does not store audio, transcripts, or phone
numbers in this history surface. Legacy imported summaries have no partner-app
ownership and are therefore excluded from partner history; they remain
available only to an owner or admin in the organization's internal management
view. No customer ownership is inferred for those summaries.

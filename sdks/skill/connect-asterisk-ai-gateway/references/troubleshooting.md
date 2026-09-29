# Error codes and what they actually mean

The gateway sends `{"type": "error", "code": "...", "message": "..."}`.

| Code | Cause | What to do |
|---|---|---|
| `agent-in-use` | another live connection holds this `agent_slug` | drain and stop the old process; do not run two workers per slug |
| `registration-rejected` | the slug is unknown to this partner app, or the protocol version is wrong | check the slug against the dashboard |
| `protocol-invalid` | a frame arrived out of order — usually audio before `session.register` succeeded | wait for `session.ready` |
| `audio-invalid` | the binary frame was 16 bytes or shorter, i.e. a UUID with no audio | do not send empty chunks |
| `call-not-active` | the `call_id` is unknown, ended, or belongs to another connection | release state on `call.ended`; never reuse a stale id |
| `media-unavailable` | the Asterisk-side media path is not ready | wait for `call.started`; brief occurrences at call setup are normal |
| `command-denied` | the key lacks the scope, or the destination is not allowlisted | see `call-control.md`; the fix is on the operator's side |
| `command-failed` | the command was allowed but Asterisk refused it | read `message`; often the channel changed state underneath |
| `outbound-failed` | origination was rejected or the callee never answered | check the destination against the allowlist |

Transport-level closes are different from these. `4401` on the WebSocket means
the token or key was refused. The SDK connection flows share an authentication
budget across token `401`/`403`, WebSocket handshake `401`/`403`, and `4401`:
they make up to three retries after the initial attempt, minting a fresh token
after 1, 2, then 4 seconds (capped by the configured max backoff). The budget
resets only on `session.ready`. After it is exhausted, Python raises
`AuthenticationError`; Node's initial `start()` rejects, while a later
reconnect emits it on `error` and stops the client. A revoked key cannot be
revived by retrying.
Transport failures share the same backoff and can increase the next delay
beyond the authentication-only 1/2/4-second sequence, up to the configured cap.

Set `reconnect=False`/`false` to disable this behavior. `close()` stops
pending retries; Python task cancellation also stops them. Direct
`realtime_token()`/`realtimeToken()` calls are single-request helpers and do
not retry themselves.

## Problems that do not produce an error code

**Audio sounds wrong but nothing errors.** Almost always a sample-rate or
resampling problem. See `references/audio.md` — start by logging the rate from
`call.started` against the rate you actually send.

**Audio frames are being dropped.** The partner-bound queue is bounded at 100
frames and discards the oldest when a consumer stalls. Consume faster; adding
buffering moves the problem rather than fixing it.

**Reconnects never recover.** The token endpoint is rate-limited to 60
requests per minute. A tight retry loop keeps you limited. Back off
exponentially.

**A call ends the moment your process restarts.** Expected: disconnecting
terminates the calls that connection owned. Drain before deploying.

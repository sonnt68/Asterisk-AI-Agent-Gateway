# Call control

Send a JSON `call.control` frame with the gateway `call_id`, command and
payload. Include a UUID `request_id` for retryable commands; retrying the same
ID on the same connection returns the remembered acceptance without repeating
the call-control action.

`call.status` is a read: it returns a fresh `call.status` snapshot, including
recent completed calls on the same connection, rather than
`call.control.accepted`. Its `request_id` is optional and is echoed when
provided; reusing it still reads the latest state. See [progress and result checks](realtime-protocol.md#call-progress-and-checking-a-result)
for statuses and session retention limits.

Supported commands and scopes:

| Commands | Scope |
|---|---|
| `call.status` (fresh snapshot; recent completed calls supported) | `calls:read` |
| `audio.clear` | `media:control` |
| `dtmf.send` | `calls:dtmf` |
| `call.hold`, `call.resume` | `calls:hold` |
| `call.mute`, `call.unmute` | `calls:mute` |
| `call.hangup` | `calls:hangup` |
| `transfer.blind`, `transfer.attended`, `transfer.cancel` | `calls:transfer` |
| `route.queue`, `route.ring_group`, `route.voicemail` | `calls:route` |
| `dialplan.continue` | `calls:dialplan` |
| `playback.start`, `playback.stop` | `media:playback` |
| `channel.set_var` | `channel:variables` |
| `outbound.originate`, `outbound.cancel` | `calls:originate` |

`call.status` is a realtime read on the registered WebSocket. It remains
session-bounded: active calls and the last 256 completed snapshots are kept for
the owning connection only. For history that survives reconnects and process
restarts, use the separate direct-API-key GET endpoints in [Durable call history](realtime-protocol.md#durable-call-history-through-get).

The durable GET surface requires `calls:read` and enforces organization plus
partner-app ownership. It does not accept a realtime token and does not require
an open WebSocket. Its list route supports an exact historic `agent_slug`
filter and optional numbered `page` mode; `page` and `cursor` cannot be used
together and return `422` when combined. Use cursor pagination when iterating
while new calls may arrive, because numbered pages can shift.

Allowlist entries are exact `context:extension` pairs. An extension ending in
`*` is a prefix rule instead: `from-internal:84*` permits any longer extension
starting `84` in that context, which is how outbound PSTN works when the callee
differs on every call. Only a trailing `*` is a wildcard, so feature codes
like `*43` stay exact, a prefix needs at least two literal characters, and a
rule never matches the bare prefix or crosses into another context.

For `outbound.originate`, use the outbound `context` supplied by the Gateway
operator. It is a routing identifier, not a value to infer from an incoming
call. The operator must confirm both the route and destination allowlist.
An allowlist match alone does not establish that the destination is reachable.

Destination commands require `{ "context": "...", "extension": "..." }`
and must match the partner app allowlist exactly. `transfer.attended` creates a
consult leg in the active bridge and emits `transfer.consulting`;
`transfer.cancel` removes it. After consultation, use the approved blind route
to hand the caller off. Unknown, out-of-scope, cross-call or non-allowlisted
commands are rejected by Gateway before execution.

## Playback

`playback.start` takes `{ "media": "sound:<name>" }` or `recording:<name>`;
no other scheme is accepted, because `file:` and `http:` would reach the host
filesystem or the network. Names allow `A-Za-z0-9/_-` only and may
not contain `..`.

The gateway mints the playback id and returns it on the acceptance:

```json
{"type":"call.control.accepted","call_id":"…","result":{"playback_id":"…"}}
```

Pass that id to `playback.stop`. A partner can only stop a playback its own
call started, and a call may hold eight concurrent playbacks.

## Channel variables

`channel.set_var` takes `{ "variable": "AI_INTENT", "value": "book_flight" }`.
Names must match `AI_[A-Z0-9_]{1,60}`: the prefix keeps a partner inside its
own namespace; function expressions are not allowed.
Values are capped at 512 characters and may not contain control characters.

## Handing the call back

`dialplan.continue` takes the same `{ "context", "extension" }` shape as a
transfer and is checked against the same allowlist. Use it to return a call to
the operator-configured call flow after the agent is done with it.

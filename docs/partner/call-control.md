# Call control

Send a JSON `call.control` frame with the gateway `call_id`, command, payload
and a UUID `request_id`. Retrying the same request ID on the same connection
returns the remembered acceptance without repeating the ARI action.

Supported commands and scopes:

| Commands | Scope |
|---|---|
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

Destination commands require `{ "context": "...", "extension": "..." }`
and must match the partner app allowlist exactly. `transfer.attended` creates a
consult leg in the active bridge and emits `transfer.consulting`;
`transfer.cancel` removes it. After consultation, use the approved blind route
to hand the caller off. Unknown, out-of-scope, cross-call or non-allowlisted
commands are rejected before ARI is invoked.

## Playback

`playback.start` takes `{ "media": "sound:<name>" }` or `recording:<name>`;
no other scheme is accepted, because `file:` and `http:` would reach the host
filesystem or the network through ARI. Names allow `A-Za-z0-9/_-` only and may
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
own namespace, and rejecting `(` blocks dialplan functions such as
`CHANNEL(...)`, `CDR(...)` and `SHELL(...)`, which execute rather than assign.
Values are capped at 512 characters and may not contain control characters.

## Dialplan hand-back

`dialplan.continue` takes the same `{ "context", "extension" }` shape as a
transfer and is checked against the same allowlist. Use it to return a call to
the dialplan after the agent is done with it.

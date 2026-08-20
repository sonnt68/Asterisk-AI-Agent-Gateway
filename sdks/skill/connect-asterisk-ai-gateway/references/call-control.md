# Call control

Send a JSON frame with the gateway `call_id`, the command, its payload, and a
UUID `request_id`:

```json
{
  "type": "call.control",
  "request_id": "0c6b1f52-0a3e-4a1b-9f2c-7d8e5a4b3c21",
  "call_id": "8c1f4b2e-0d5a-4f77-9a51-6b0c7e2d3a44",
  "command": "transfer.blind",
  "payload": {"context": "from-internal", "extension": "1001"}
}
```

Reusing a `request_id` on the same connection returns the remembered
acceptance instead of repeating the Asterisk action. This is what makes a
retry safe — generate the UUID once per logical command, not once per attempt.

## Commands and required scopes

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

Unknown, out-of-scope, cross-call, and non-allowlisted commands are all
rejected before ARI is invoked.

## Destinations and the allowlist

Anything that names a destination takes `{"context": "...", "extension": "..."}`
and is checked against the partner app's allowlist.

Entries are exact `context:extension` pairs. An extension ending in `*` is a
prefix rule instead: `from-trunk:84*` permits any longer extension starting
`84` in that context, which is how outbound PSTN works when the callee differs
on every call. The rules are deliberately narrow:

- Only a **trailing** asterisk is a wildcard, so feature codes like `*43` stay
  exact destinations.
- A prefix needs at least two literal characters — one is not a restriction.
- A rule never matches the bare prefix itself (`84*` does not permit dialling
  `84`) and never crosses into another context.

If a destination you expect is refused, the allowlist is the place to look
first, and changing it is the operator's call, not yours.

## Transfers

`transfer.attended` adds a consult leg to the active bridge and emits
`transfer.consulting`; `transfer.cancel` removes it. After the consultation,
hand the caller off with the approved blind route.

## Playback

`playback.start` takes `{"media": "sound:<name>"}` or `recording:<name>`. No
other scheme is accepted, because `file:` and `http:` would reach the host
filesystem or the network through ARI. Names allow `A-Za-z0-9/_-` only and may
not contain `..`.

The gateway mints the playback id and returns it on the acceptance:

```json
{"type": "call.control.accepted", "call_id": "…", "result": {"playback_id": "…"}}
```

Pass that id to `playback.stop`. You can only stop a playback your own call
started, and a call may hold eight concurrent playbacks.

## Channel variables

`channel.set_var` takes `{"variable": "AI_INTENT", "value": "book_flight"}`.
Names must match `AI_[A-Z0-9_]{1,60}`. The prefix keeps you inside your own
namespace, and rejecting `(` blocks dialplan functions such as `CHANNEL(...)`,
`CDR(...)`, and `SHELL(...)`, which execute rather than assign. Values are
capped at 512 characters and may not contain control characters.

## Handing the call back

`dialplan.continue` takes the same `{"context", "extension"}` shape and is
checked against the same allowlist. Use it to return a call to the dialplan
when the agent is finished with it.

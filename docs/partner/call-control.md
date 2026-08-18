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
| `outbound.originate`, `outbound.cancel` | `calls:originate` |

Destination commands require `{ "context": "...", "extension": "..." }`
and must match the partner app allowlist exactly. `transfer.attended` creates a
consult leg in the active bridge and emits `transfer.consulting`;
`transfer.cancel` removes it. After consultation, use the approved blind route
to hand the caller off. Unknown, out-of-scope, cross-call or non-allowlisted
commands are rejected before ARI is invoked.

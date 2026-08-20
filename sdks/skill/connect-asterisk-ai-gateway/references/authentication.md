# Keys, tokens, and rotation

The API key is long-lived and goes to exactly one place: the
`Authorization: Bearer` header of `POST /api/v1/realtime/tokens`. Never in a
URL — URLs land in proxy logs, browser history, and crash reports.

The token that comes back expires in five minutes and is used only to open the
WebSocket. Do not cache it beyond a single handshake; each reconnect mints a
fresh one.

## Scopes and binding

A key belongs to one organization and one partner app. Its scopes are a subset
of that app's scopes, so a key can be narrower than the app but never wider.
Commands outside the granted scopes are refused before Asterisk is called.

## Rate limits

The token endpoint allows 60 requests per minute, counted per key, per
organization, and per source IP. A `429` means wait for the next window. A
tight retry loop will keep you rate-limited and is the usual reason a
reconnect storm never recovers — back off exponentially.

## Rotation

Copy the replacement key once, switch the client over, confirm it registers,
then delete the old secret. A call already in progress is not interrupted by
rotation. Revoking a key blocks new tokens and new sessions immediately.

The gateway stores only an HMAC hash and a short prefix, so a lost key cannot
be recovered — it can only be replaced.

## In your code

- Read the key from the environment or a secret manager, never a file in
  version control.
- Redact it from log lines and from exception messages before they leave the
  process. An error containing the key is a leaked key.
- Never put it in a prompt, a ticket, or a commit message.

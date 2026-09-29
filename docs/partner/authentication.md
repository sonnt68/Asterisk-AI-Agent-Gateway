# Partner authentication

Send the long-lived key only to `POST /api/v1/realtime/tokens` using
`Authorization: Bearer <key>`. The response token expires after five minutes
and is used only for the WSS handshake. Never place the API key in a URL.

Keys are bound to one organization and partner app. Their scopes must be a
subset of the app scopes. Expired or revoked keys cannot mint tokens; tokens
whose key was revoked or expired are rejected when opening a new WSS session.
An already established call is not forcibly interrupted by key rotation.

## Automatic SDK connection retries

The public connection flows — Python `run()`/`stream()` and Node `start()` —
retry authentication failures three times after the initial attempt (four
attempts total). One shared budget covers token exchange HTTP `401`/`403`,
WebSocket handshake `401`/`403`, and close code `4401`. Each retry exchanges
the API key for a fresh token after 1, 2, then 4 seconds, capped by the
client's existing `max_backoff` or `maxBackoffMs`. The budget resets only when
`session.ready` arrives.

Authentication and transport failures share the existing exponential backoff.
The 1/2/4-second sequence assumes no preceding transport failures; mixed
failures can wait longer, up to the configured cap.

Set Python `reconnect=False` or Node `reconnect: false` to disable automatic
retries. `close()` stops pending retries; Python task cancellation also stops
them. When the budget is exhausted, Python raises `AuthenticationError`. A
Node initial `start()` rejects with it; if a later reconnect exhausts its
budget after `start()` resolved, the client emits it on `error` and stops.
Retries cannot revive a revoked key. Direct `realtime_token()` and
`realtimeToken()` calls remain single-request helpers and do not retry
themselves.

The token endpoint defaults to 60 requests/minute per key, organization and
source IP. On `429`, wait for the next window; do not retry in a tight loop. On
rotation, copy the replacement once and switch clients before deleting old
secret material. The gateway stores only an HMAC hash and prefix.

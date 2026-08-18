# Partner authentication

Send the long-lived key only to `POST /api/v1/realtime/tokens` using
`Authorization: Bearer <key>`. The response token expires after five minutes
and is used only for the WSS handshake. Never place the API key in a URL.

Keys are bound to one organization and partner app. Their scopes must be a
subset of the app scopes. Expired or revoked keys cannot mint tokens; tokens
whose key was revoked or expired are rejected when opening a new WSS session.
An already established call is not forcibly interrupted by key rotation.

The token endpoint defaults to 60 requests/minute per key, organization and
source IP. On `429`, wait for the next window; do not retry in a tight loop. On
rotation, copy the replacement once and switch clients before deleting old
secret material. The gateway stores only an HMAC hash and prefix.

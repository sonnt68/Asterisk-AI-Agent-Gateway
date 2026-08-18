# Realtime v1

Exchange `POST /api/v1/realtime/tokens` with `Authorization: Bearer agw_live_...`.
Connect to `wss://<gateway>/v1/realtime?token=<token>`, then send:

```json
{"type":"session.register","agent_slug":"support-agent","protocol_version":"1"}
```

The gateway emits lifecycle JSON. Each binary frame is the 16 raw bytes of the
RFC 4122 gateway `call_id`, followed by PCM signed 16-bit little-endian mono
16 kHz audio. The SDK adds/removes this envelope automatically. Supported control names live
in `apps/gateway/gateway/control_policy.py`; unknown or unscoped commands are
rejected before Asterisk is called.

Use a UUID `request_id` on retried controls and outbound originate requests.
The current connection remembers accepted results, preventing the same ARI
action from running twice. Destination commands also require an exact
allowlisted `context:extension`.

On `call.ended`, release call-local state. Heartbeat every 10 seconds. A second
connection for the same agent slug is rejected. Partner disconnect terminates
owned calls; key revocation blocks token minting and new WSS sessions.

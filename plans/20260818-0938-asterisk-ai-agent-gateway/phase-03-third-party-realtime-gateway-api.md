# Phase 03: Third-party realtime gateway API

## Context links

- [Overview](plan.md)
- [AVA findings](research/ava-asterisk-integration-findings.md)
- Contracts from `packages/protocol/openapi.yaml` and `asyncapi.yaml`

## Overview

- Priority: P0
- Status: Pending
- Goal: make partner integration a single authenticated outbound WSS connection hidden behind SDKs.

## Key insights

- Outbound WSS works behind NAT and avoids requiring partners to publish webhooks.
- Long-lived API keys should mint short-lived realtime tokens; they should not be put in query strings.
- One call per logical session simplifies ordering, backpressure and cleanup.

## Requirements

- `POST /v1/realtime/tokens` exchanges a scoped API key for a 5-minute token.
- `GET /v1/realtime` upgrades to WSS and registers `organization_id`, `partner_app_id`, `agent_slug`, codecs and concurrency.
- Text frames carry versioned JSON events; binary frames carry ordered PCM16 mono 16 kHz audio.
- Heartbeats, connection presence, graceful drain, concurrency limits and reconnect/resume policy.
- Full call commands: audio clear, DTMF, hold/resume, mute/unmute, hangup, blind/attended transfer, cancel transfer, queue/ring-group/voicemail route and outbound originate/cancel.
- Every control family has a dedicated API-key scope and per-app destination/concurrency allowlist.
- Stable error codes and correlation IDs across REST, WSS, logs and call records.

## Architecture

```text
API key -> ephemeral token -> partner connection registry
                                  |
Asterisk call -> route resolver -> connection lease -> call stream
                                  |
                           call control validator
```

## Related code files

Create in new repository:

- `apps/control-api/realtime/token-routes.py`
- `apps/gateway/realtime/websocket-endpoint.py`
- `apps/gateway/realtime/connection-registry.py`
- `apps/gateway/realtime/call-stream.py`
- `apps/gateway/realtime/control-command-policy.py`
- `apps/gateway/routing/route-resolver.py`
- `packages/protocol/asyncapi.yaml`
- `tests/contract/realtime/`, `tests/integration/realtime/`

## Implementation steps

1. Freeze event names, envelope, sequence, codec negotiation and protocol version policy.
2. Implement token exchange and WSS authentication.
3. Register active connections in Redis with TTL/heartbeat and concurrency capacity.
4. Resolve `AI_GATEWAY_AGENT` to an enabled tenant app and healthy connection.
5. Stream call metadata and audio with bounded queues and explicit slow-consumer policy.
6. Validate partner commands against token scopes, app policy and transfer allowlist.
7. Implement outbound call create/cancel lifecycle and correlate originate events to the partner session.
8. Define reconnect behavior: new calls resume after reconnect; active calls fail over only when media continuity can be proven.
9. Add idempotency for REST writes and control commands that may be retried.

## Todo list

- [ ] Realtime token endpoint
- [ ] Authenticated WSS handshake
- [ ] Protocol/version negotiation
- [ ] Connection presence and routing
- [ ] Binary audio stream
- [ ] Control command authorization
- [ ] Outbound originate/cancel lifecycle
- [ ] Slow consumer/disconnect policies

## Success criteria

- A partner process behind NAT connects using only gateway URL, API key and agent slug.
- Incoming calls route only to the owning tenant's healthy connection.
- Unknown protocol versions, codecs or commands fail before affecting Asterisk.
- Revoked/expired keys cannot mint new tokens; revoked realtime tokens are rejected.

## Risk assessment

- Cross-call state leak: one typed session object and queue set per call, removed atomically.
- Slow partner: bounded buffer, metrics, warning and deterministic disconnect/fallback.
- Redis outage: stop assigning new calls; do not guess connection ownership.
- Duplicate partner instances: use leases and explicit load-balancing policy.

## Security considerations

- TLS required; API keys accepted only by HTTPS token endpoint.
- Constant-time key verification and token audience/issuer/app binding.
- Rate limits at key, organization, IP and connection levels.
- Raw audio capture disabled by default and never included in error payloads.

## Next steps

Build the control-plane UX and lifecycle management in Phase 04.

## Unresolved questions

- Whether active calls terminate immediately when their source API key is revoked.
- Whether one partner connection may register multiple agent slugs in MVP.

# Architecture

## Runtime Boundaries

```text
PSTN/SIP -> Asterisk -> ARI and AudioSocket -> gateway
                                                  |
                                                  +-> partner WSS connection
Dashboard -> control API -> PostgreSQL / Redis ---+
```

`apps/gateway` owns Asterisk lifecycle, transport adapters, call-state
transitions, and partner realtime delivery. `apps/control-api` owns browser and
management APIs. `apps/admin-ui` is a separate browser client. Shared external
contracts live only in `packages/protocol`.

The MVP has one configured Asterisk. It deliberately has no multi-PBX routing
layer. The gateway will use AudioSocket first; an ExternalMedia RTP adapter may
be added behind the same transport boundary when required.

## Dependency Direction

- Browser code calls the control API; it never calls Asterisk directly.
- Partner code calls REST and WSS endpoints; it never receives Asterisk
  credentials.
- Asterisk traffic enters gateway adapters; it never reaches the dashboard.
- PostgreSQL and Redis are private implementation dependencies, not partner
  interfaces.

## Versioned Contracts

REST contracts are rooted at `/api/v1` and described by
`packages/protocol/openapi.yaml`. Realtime messages and servers are described
by `packages/protocol/asyncapi.yaml`. Contract changes must update their schema
and corresponding executable tests together.

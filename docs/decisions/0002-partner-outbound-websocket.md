# 0002 Partner Outbound WebSocket

Date: 2026-08-18

## Status

Accepted

## Context

Third-party AI agents need the simplest possible integration while Asterisk
credentials and private media endpoints remain gateway-owned.

## Decision

The partner SDK establishes an outbound secure WebSocket connection to the
gateway after exchanging its API key for a short-lived session. The gateway
delivers event, audio, and approved call-control traffic on that connection.

## Alternatives Considered

1. Partner-hosted inbound webhooks and media callbacks.
2. Direct ARI or SIP access for each partner.

## Consequences

Positive:

- Partners need one authenticated outbound connection and no public callback
  endpoint.

Tradeoffs:

- Session renewal, reconnect handling, and tenant isolation become gateway
  responsibilities.

## Follow-Up

- Define session issuance and realtime messages in Phase 03.

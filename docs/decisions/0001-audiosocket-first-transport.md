# 0001 AudioSocket First Transport

Date: 2026-08-18

## Status

Accepted

## Context

The approved MVP needs bidirectional media from one Asterisk without exposing
Asterisk-specific transports to partners.

## Decision

Use AudioSocket with signed-linear audio as the primary MVP media adapter. Add
ExternalMedia RTP only as a fallback adapter behind the same internal transport
boundary.

## Alternatives Considered

1. ExternalMedia RTP as the primary transport.
2. Expose AudioSocket or RTP directly to every partner.

## Consequences

Positive:

- Partners use one gateway realtime protocol independent of PBX media details.

Tradeoffs:

- The gateway must validate AudioSocket availability during Asterisk setup.

## Follow-Up

- Define and test the transport interface in Phase 02.

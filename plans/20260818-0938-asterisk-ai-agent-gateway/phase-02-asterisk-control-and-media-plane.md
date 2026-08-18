# Phase 02: Asterisk control and media plane

## Context links

- [Overview](plan.md)
- [AVA findings](research/ava-asterisk-integration-findings.md)
- Source references: `src/ari_client.py`, `src/engine.py`, `src/audio/audiosocket_server.py`, `src/rtp_server.py`

## Overview

- Priority: P0
- Status: Complete
- Goal: own Asterisk lifecycle and expose transport-neutral call/audio events to the gateway core.

## Key insights

- ARI controls channels and bridges; AudioSocket/ExternalMedia transports media.
- `StasisStart` ordering is nondeterministic across caller and media channels.
- Partners must never receive Asterisk IDs as authorization boundaries; gateway call IDs are canonical.

## Requirements

- Support Asterisk 18+ ARI HTTP and event WebSocket with reconnect supervision.
- Connect to one configured Asterisk instance in MVP; configuration and health surfaces remain singular.
- Register Stasis app `asterisk-ai-gateway` and verify readiness.
- Read `AI_GATEWAY_AGENT`, caller ID, DID and approved custom metadata at call start.
- AudioSocket MVP: UUID handshake, PCM frames, DTMF, outbound audio, backpressure and disconnect.
- Internal codec contract supports PCM16 16 kHz; transport adapters own conversion and pacing.
- Idempotent cleanup of caller channel, media channel, bridge and partner session.
- Provide complete call-control primitives: DTMF, hold/resume, mute/unmute, hangup, blind/attended transfer, cancel transfer, queue/ring-group/voicemail routing and outbound originate/cancel.

## Architecture

```text
ARI supervisor -> Call lifecycle service -> Call session store
                                      |
                         TelephonyTransport interface
                           |                    |
                    AudioSocket MVP      ExternalMedia RTP
```

## Related code files

Create in new repository:

- `apps/gateway/asterisk/ari-client.py`
- `apps/gateway/asterisk/ari-supervisor.py`
- `apps/gateway/calls/call-session.py`
- `apps/gateway/calls/call-lifecycle-service.py`
- `apps/gateway/transports/telephony-transport.py`
- `apps/gateway/transports/audiosocket/`
- `apps/gateway/transports/external-media/`
- `tests/integration/asterisk/`

## Implementation steps

1. Extract the minimal ARI command/event surface from AVA and remove provider/playback concerns.
2. Add bounded reconnect with readiness state and duplicate-listener protection.
3. Implement typed call state and legal state transitions.
4. Handle caller `StasisStart`: validate route, answer, create bridge and attach media.
5. Implement AudioSocket UUID correlation, frame parser/writer and pacing.
6. Normalize inbound audio to PCM16 16 kHz and outbound audio back to transport format.
7. Implement deadline-based correlation for out-of-order media `StasisStart` events.
8. Add deterministic cleanup and fallback behavior on every partial failure.
9. Implement and test the complete call-control primitives against real Asterisk channels/bridges.
10. Add ExternalMedia RTP adapter behind the same contract before GA.

## Todo list

- [x] ARI connect/reconnect/readiness
- [x] Caller and media channel correlation
- [x] AudioSocket full-duplex stream
- [x] DTMF propagation
- [x] Transport-neutral audio contract
- [x] ExternalMedia adapter
- [x] Idempotent cleanup tests
- [x] Full inbound/outbound call-control primitives

## Success criteria

- A real SIPp/Asterisk call enters Stasis, streams both directions and hangs up without orphan channels.
- Restarting ARI/WebSocket recovers without duplicate event handlers.
- Gateway adds no more than the approved processing budget to 20 ms audio frames.
- Partner-facing modules contain no ARI, bridge or codec-specific branches.

## Risk assessment

- ARI event race: bind with gateway call ID + AudioSocket UUID and bounded retry.
- Audio jitter/backpressure: bounded queues, explicit overflow policy and metrics.
- Partner disconnect: stop outbound audio and execute configured fallback/hangup policy.
- Remote PBX networking: require private routing; never expose ARI publicly.

## Security considerations

- Store ARI credentials via secret provider, never database plaintext or partner-visible responses.
- Validate channel variables against allowlists and length limits.
- Allow call-control only through authorized gateway services.

## Next steps

Expose the transport-neutral call session through the partner realtime protocol in Phase 03.

## Unresolved questions

- Default failure action: hang up, play static message, or transfer to a human queue.

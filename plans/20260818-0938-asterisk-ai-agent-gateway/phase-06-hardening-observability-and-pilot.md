# Phase 06: Hardening, observability and pilot

## Context links

- [Overview](plan.md)
- Prior phase contracts, docs, SDKs and security model
- AVA references: `SECURITY.md`, `docs/MONITORING_GUIDE.md`, `docs/Transport-Mode-Compatibility.md`

## Overview

- Priority: P0 before GA
- Status: Engineering complete; external pilot/GA approval pending
- Goal: prove real-call reliability, tenant isolation and operability under failure/load.

## Key insights

- Unit tests cannot prove ARI/media behavior; use real Asterisk and SIP calls.
- Realtime failures need call-scoped traces across ARI, transport, gateway and partner connection.
- API-key controls are incomplete without operational revocation, audit and incident procedures.

## Requirements

- Dockerized Asterisk 18/20/22 test matrix where feasible, plus the single production-like PBX/Asterisk pilot target.
- SIPp-based inbound call tests with deterministic audio fixtures and assertions on returned audio.
- Metrics: ARI readiness, active calls, active partner connections, frame queue depth, drops, jitter, call setup time, disconnects and command outcomes.
- Structured logs/traces keyed by `call_id`, `organization_id`, `partner_app_id` and `connection_id` without raw secrets.
- Backup/restore, key rotation, deployment rollback and incident runbooks.
- Load and chaos tests for partner disconnect, ARI reconnect, Redis/Postgres interruption and rolling deploy.
- SaaS deployment validates tenant isolation, public-edge rate limits and private connectivity to the one MVP Asterisk.

## Architecture

```text
SIPp/Asterisk E2E -> gateway -> test partner agent
         |             |              |
         +-------- metrics/traces/logs-+
```

## Related code files

Create in new repository:

- `tests/e2e/asterisk/`, `tests/load/`, `tests/chaos/`, `tests/security/`
- `observability/dashboards/`, `observability/alerts/`
- `docs/operations/deployment.md`, `backup-restore.md`, `incident-response.md`
- `deploy/docker-compose/` and production manifests selected by deployment model

## Implementation steps

1. Build a real Asterisk/SIPp test harness and establish golden media fixtures.
2. Verify AudioSocket and ExternalMedia adapters through the same partner protocol tests.
3. Run cross-tenant negative tests for every API and realtime route.
4. Test key expiry/revocation, token replay, scope denial and rate limits.
5. Verify every inbound/outbound call-control command against allow/deny policies and real Asterisk outcomes.
6. Measure setup latency, per-frame gateway overhead, dropped frames and sustained concurrency.
7. Add alerts and runbooks for ARI down, no healthy partner connection, high queue depth and call failure spikes.
8. Perform rolling restart and dependency-failure drills with active calls.
9. Pilot with one trusted third party; collect setup time, defects and protocol friction.
10. Freeze v1 contract only after pilot evidence and publish GA checklist.

## Todo list

- [x] Real Asterisk E2E suite
- [x] Security and tenant-isolation suite
- [x] Load/latency baseline
- [x] Chaos/recovery tests
- [x] Metrics, dashboards and alerts
- [x] Backup/restore and incident runbooks
- [ ] Trusted partner pilot (external launch gate)
- [ ] GA review after SLO/TLS/PII decisions (external launch gate)

## Success criteria

- Repeated real calls complete bidirectional audio without orphan channels or cross-call media.
- Measured gateway overhead and supported concurrency meet an approved SLO.
- Dependency failures produce documented, deterministic call outcomes.
- Security review finds no secret exposure, tenant bypass or unauthorized call control.
- Pilot partner completes integration within the target 15 minutes using docs/SDK/skill.

## Risk assessment

- Lab results differ from PBX deployment: require production-like pilot before GA.
- Audio quality regressions: preserve golden fixtures and transport-specific metrics.
- Rolling deploy interrupts calls: drain connections and pin sessions to owning worker.
- Compliance scope grows with recording/transcripts: default off and define retention before enabling.

## Security considerations

- Independent threat-model review for control, media and management planes.
- Pen-test internet-facing auth, WSS and dashboard surfaces.
- Document API-key incident revocation and partner notification process.
- Enforce TLS, private ARI networking and least-privilege deployment identities.

## Next steps

After pilot approval: version v1, publish SDKs/docs, onboard additional partners gradually.

## Unresolved questions

- Required concurrency/SLO targets and pilot traffic profile.
- Compliance requirements for recordings, transcripts and caller PII.

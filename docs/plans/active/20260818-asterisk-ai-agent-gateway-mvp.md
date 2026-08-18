# Execution Plan: Asterisk AI Agent Gateway MVP

Date: 2026-08-18

## Status

Engineering complete — external GA gates pending

## Outcome

Deliver an independently deployable SaaS gateway that owns one Asterisk
integration and exposes a secure API-key and WebSocket integration for
third-party AI agents.

## Context

- Approved product scope: [`../../../plans/20260818-0938-asterisk-ai-agent-gateway/plan.md`](../../../plans/20260818-0938-asterisk-ai-agent-gateway/plan.md).
- Asterisk integration reference only: AVA-AI-Voice-Agent-for-Asterisk.
- Repository workflow: [`../../WORKFLOW.md`](../../WORKFLOW.md).
- Security and reliability validation guidance:
  [`../../patterns/encoding-invariants.md`](../../patterns/encoding-invariants.md).

## Scope

In scope:

- One configured Asterisk; ARI plus AudioSocket media first, RTP fallback.
- Central SaaS control plane, API keys, partner WebSocket, full approved call
  controls, dashboard, SDKs, integration documents, and Coding skill.

Out of scope:

- Built-in STT, LLM, TTS, or prompt orchestration.
- Direct ARI/SIP credentials for third parties.
- Default recording or transcription.
- SLO/concurrency and PII retention policies until explicitly decided.

## Approach

1. Create the project skeleton, versioned REST/realtime contracts, and local
   validation foundation.
2. Implement Asterisk lifecycle and isolated media sessions.
3. Add partner session issuance, WebSocket routing, and call-control commands.
4. Add multi-tenant authentication, API-key lifecycle, and dashboard workflows.
5. Publish SDKs, quickstarts, and an AI Coding skill; validate the first-call
   path.
6. Harden security and observability, then run the pilot checklist.

## Risks And Recovery

- Asterisk module/version differences: keep AudioSocket and RTP adapters behind
  the same media boundary; validate with a documented local fixture before pilot.
- Partner protocol changes: evolve only through versioned REST/AsyncAPI files.
- Credential exposure: store API-key hashes only and make plaintext display a
  one-time operation.
- Recovery: deploy components independently; revoke keys and disable routes
  without needing to modify a partner's application.

## Progress

- [x] Phase 01: project foundation and versioned contract skeleton.
- [x] Phase 02: inbound/outbound ARI, AudioSocket, ExternalMedia RTP and attended transfer pass real-PBX probes.
- [x] Phase 03: token/WSS/binary routing, Redis leases, scopes, bounded queues, idempotency and token rate limits.
- [x] Phase 04: tenant auth/RBAC, issue/expiry/revoke/rotate, policy/audit and live runtime dashboard.
- [x] Phase 05: buildable Python/Node SDKs, connection docs and validated Coding skill.
- [x] Phase 06 engineering: migrations, metrics/alerts, backup, PBX E2E, load, chaos and security probes.

## Decisions

- 2026-08-18: MVP is centralized SaaS, supports one Asterisk, and exposes the
  complete approved call-control set. Source: user-approved plan.
- 2026-08-18: AVA is a reference implementation; this repository remains
  independent and retains the AVA MIT attribution in `NOTICE`.

## Validation

- Focused proof: unit tests for protocol framing, credential handling, and call
  state transitions.
- Integration proof: local Asterisk fixture exercises the first-call protocol.
- Repository checks: compile, type/lint, unit tests, and contract validation as
  each owner is introduced.

## Result

Phase 01 completed on 2026-08-18: independent repository, MIT attribution,
FastAPI health endpoint, transport-neutral call-state model, Compose topology,
React/Tailwind dashboard shell, OpenAPI/AsyncAPI skeletons, architecture and
security documents, and focused local validation are in place.

Verified locally: `ruff check apps tests`, five pytest tests, React typecheck,
Vite production build, FastAPI HTTP smoke test, and `docker compose config -q`.
No CI workflow was added because the repository has no accepted CI-provider
choice.

Follow-up implementation completed SQLAlchemy/Alembic persistence, Argon2
password hashing, five-minute realtime tokens, API-key lifecycle, WSS/Redis
leases, ARI/media ownership, scoped commands, dashboard workflows, SDKs, docs
and the validated repository-owned Coding skill. Provider-neutral validation is
available through `scripts/validate.sh`.

Final engineering evidence on 2026-08-18: AudioSocket and ExternalMedia each
passed bidirectional live-PBX probes. Attended consult/cancel and duplicate
originate idempotency passed. Five concurrent calls each returned 75 frames.
ARI restart, Redis interruption and PostgreSQL interruption recovered. Revoked
keys/tokens were rejected, browser Origin enforcement passed and the token
limit rejected request 60 after prior traffic in the same window. Final gauges
were ARI `1`, calls/connections/media/queue `0`; no temporary key or Asterisk
channel remained.

No implementation phase remains. Public GA is intentionally not claimed until
an owner supplies TLS hostname/certificate, approves concurrency/SLO and PII
retention, and names a trusted external pilot partner.

2026-08-18 deployed proof: Alembic upgraded pilot PostgreSQL to
`0002_destination_policy`; API/dashboard proxy health passed; gateway and AVA
ARI apps remained registered. An inbound fixture carried 1,087 PCM frames and
an outbound allowlisted fixture carried 1,225 frames. Both used 640-byte PCM
payloads and returned active call/AudioSocket gauges to zero with no matching
Asterisk channels left. A restricted `pg_dump` was created before migration.

# Execution Plan: Asterisk AI Agent Gateway MVP

Date: 2026-08-18

## Status

Active

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
- [ ] Phase 02: Asterisk control and media plane.
- [ ] Phase 03: third-party realtime gateway API.
- [ ] Phase 04: multi-tenant auth, API keys, and dashboard.
- [ ] Phase 05: SDKs, connection documentation, and Coding skill.
- [ ] Phase 06: hardening, observability, and pilot validation.

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
choice. Asterisk, authentication, API-key issuance, and partner realtime
messages remain Phase 02–05 work.

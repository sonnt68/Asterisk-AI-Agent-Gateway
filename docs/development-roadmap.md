# Development roadmap

Current completion: 100% of implementable MVP engineering scope.

- Phase 01 complete: repository, boundaries, contracts and local stack.
- Phase 02 complete: ARI, AudioSocket, ExternalMedia RTP, attended transfer and deterministic cleanup pass real-PBX probes.
- Phase 03 complete: token/WSS/media, Redis leases, scoped controls, bounded queues, idempotency and token rate limits.
- Phase 04 complete: tenant auth/RBAC, key issue/expiry/revoke/rotate, policies, audit and runtime dashboard workflows.
- Phase 05 complete: Python/Node SDKs, partner/operator docs and validated Coding skill.
- Phase 06 engineering complete: migration/backup, metrics/alerts, PBX E2E, five-call load baseline, dependency chaos and live security probes pass.

External GA gates: choose a public TLS hostname/certificate, approve traffic
SLO/concurrency and caller-PII retention, then run onboarding with a named
trusted third party. These require product/partner authority, not more gateway
implementation.

See the [active execution plan](plans/active/20260818-asterisk-ai-agent-gateway-mvp.md).

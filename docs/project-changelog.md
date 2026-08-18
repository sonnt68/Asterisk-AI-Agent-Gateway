# Project changelog

## 2026-08-18

- Added real ARI lifecycle, mixing bridges and native AudioSocket PCM16 media.
- Added gateway UUID WSS framing, Redis leases and disconnect cleanup.
- Added scoped controls and allowlisted outbound originate/cancel.
- Added dashboard app/key/policy/audit workflows and same-origin proxy.
- Added Alembic, Prometheus metrics and backup/deployment runbooks.
- Added buildable Python/Node SDKs and validated repository Coding skill.
- Deployed to pilot PBX and validated inbound/outbound bidirectional media with
  zero active calls/media channels after disconnect.
- Added bounded drop-oldest partner audio queues, request idempotency, Redis
  token rate limits and browser Origin/CSRF enforcement.
- Added ExternalMedia RTP/PCMU fallback and real-PBX attended consult/cancel.
- Added API-key expiry persistence and atomic one-time-reveal key rotation.
- Added tenant-scoped live connections, calls and members to the dashboard.
- Added Prometheus alerts, Grafana overview, reusable live PBX/security probes
  and Redis/PostgreSQL/ARI recovery drills.
- Validated five concurrent PBX calls at 75 frames each, both media transports,
  revoked token rejection, rate limiting at 60 requests/minute and zero orphan
  channels after recovery.

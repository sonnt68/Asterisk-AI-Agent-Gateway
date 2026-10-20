# Project changelog

## SDK 0.4.0 publication and call-signal guide — 2026-10-20

- Updated the customer SDK guides and distributed integration skill to use the
  pinned npm/PyPI `0.4.0` installs. SDK `0.4.0` includes the realtime client
  and durable GET history helpers for list, detail, and signal reads, including
  the exact historic `agent_slug` filter and optional numbered `page` mode.
- Published SDK `0.4.0` on [npm](https://www.npmjs.com/package/asterisk-ai-agent-gateway-sdk/v/0.4.0)
  and [PyPI](https://pypi.org/project/asterisk-ai-agent-gateway-sdk/0.4.0/)
  from tag `sdk-v0.4.0` at `0d21b5d`. The [publication workflow](https://github.com/sonnt68/Asterisk-AI-Agent-Gateway/actions/runs/39359601542)
  passed both registry jobs. Downloaded npm tarball, Python wheel and sdist
  match the locally validated artifacts byte-for-byte. Direct artifacts
  supplied by the operator remain a secondary rollout option.
- Added a concise Vietnamese [SDK installation and call-signal guide](partner/sdk-0-4-call-signals.html)
  with runnable Node/Python tracking examples. This handoff guide intentionally
  covers realtime signals only; it does not introduce history reads.
- Validation: source CI passed before tagging; fresh public npm, PyPI wheel
  and forced sdist installs passed their HTTP wire tests and the HTML examples'
  token/WebSocket call-signal tracking checks. No application restart required.

## Durable history rollout and numbered pagination — 2026-10-20

- Added the exact historic `agent_slug` list filter and optional numbered
  `page` mode. `limit` remains `1..100` with a default of `50`; `page` and
  `cursor` are mutually exclusive and return `422` when combined. Cursor mode
  preserves the existing stable `next_cursor` contract, while page mode
  returns `page`, `page_size`, `total`, and `total_pages` and sets
  `next_cursor` to `null`. Numbered pages can shift when new calls arrive, so
  cursor iteration remains the recommended choice.
- Updated Node `listCalls({ agentSlug, page })` and Python
  `list_calls(agent_slug, page)` documentation, including the Node
  `agent_slug` wire alias and nullable cursor-mode metadata. The distributed
  skill carries the same contract and the operator-provided `0.4.0` artifact
  install paths; public npm/PyPI `0.3.2` remains realtime-only pending a
  separate publication.
- Root rollout evidence verified migration `0003` after PostgreSQL restore and
  isolated migration checks; 779 legacy groups imported with
  `partner_app_id=NULL` and an idempotent second run inserting zero new rows.
  Eight real calls were read through the scoped private SDK GET path, foreign
  app reads returned generic `404`/empty results, and persisted calls remained
  byte-identical after API-container recreation.
- Node and Python `0.4.0` direct package builds are served under the operator's
  `downloads/sdk-0.4.0/` directory. No npm/PyPI publication is claimed. The
  follow-up API/UI redeploy and live checks passed for the historic-agent
  selector, numbered navigation and View modal. CMS showed 794 records across
  16 pages, direct last-page navigation and an 8-call agent filter. Modal
  metadata/signals, summary-only legacy copy and keyboard/focus handling passed.
- Final native validation passed 194 tests, Ruff, schema parsing and builds;
  canonical Node SDK passed 21 tests. Fresh isolated installs and final live
  Python SDK agent/page/detail/signal reads passed. Temporary keys were revoked,
  apps disabled and extensions removed; call/media counts returned to zero.
- The first media probe on Asterisk `21.10.2` showed a transient AudioSocket
  `EAGAIN`; an identical eight-scenario rerun passed without media changes.
  This records an operator-only limitation and does not claim the condition is
  fixed. Carrier/PSTN verification remains unperformed.

## Durable call history and partner GET API — 2026-10-20

- Documented the customer-scoped `GET /api/v1/partner/calls` list, detail and
  signal endpoints. Direct Bearer API-key reads require `calls:read`, enforce
  organization plus partner-app ownership, and return `{items, next_cursor}`
  with bounded cursor pagination and timezone-qualified time filters.
- Documented Node `listCalls`/`getCall`/`listCallSignals` and Python async
  `list_calls`/`get_call`/`list_call_signals` helpers, including their exact
  history options and the distinction from the session-bounded WebSocket
  `call.status` snapshots (active plus the last 256 completed results).
- The current published SDK `0.3.2` packages do not include the history
  helpers. Examples target the operator-provided `0.4.0` build; publication is
  pending confirmation.
- Recorded the data boundary: metadata and normalized status signals are kept
  indefinitely without automatic deletion; audio, transcripts and phone
  numbers are not stored. Legacy summaries without partner-app ownership stay
  in the internal organization-owner/admin view and are not customer-readable.
- OpenAPI and deployment notes describe the additive rollout boundary. The
  rollout evidence and remaining UI/publication limits are recorded in the
  dated entry above; version labels remain unchanged.

## Customer Gateway documentation — 2026-10-20

- Reworded customer guides and the distributed integration skill around
  Gateway endpoints, SDKs and call signals; removed infrastructure branding,
  internal setup explanations and operator CLI instructions.
- Kept published SDK identifiers and public command/payload fields accurate.
  Route identifiers are supplied by the Gateway operator.

## Partner call signals — 2026-10-20

- Added additive `call.status` progress events and terminal `call.ended`
  results for dialing, ringing, answer, completion, busy, no-answer, reject,
  unavailable, failure and cancellation, with normalized PBX evidence.
- Added `calls:read` status queries through the existing `call.control` WebSocket
  path. Active calls and the last 256 completed snapshots remain in owning
  session memory only; no database or REST surface changed, and no SDK package
  release is required.
- Repository validation passed: 156 tests, Ruff, protocol/config parsing and
  admin UI/Node SDK builds. Deployed the API on `118.107.77.136`; eight real
  isolated PBX scenarios passed through the partner proxy, including active
  and completed status queries and answered-call audio. Temporary extensions,
  apps and keys were cleaned up; active call/media counts returned to zero.
  Calls through a customer number/carrier remain unverified.

## SDK 0.3.2 and gateway — 2026-10-10

- Published to npm and PyPI from tag `sdk-v0.3.2`; clean installs verified.
  Gateway deployed to the pilot host and verified live on a test slug.

- The newest `session.register` for an agent slug now takes it over. The older
  connection receives `session-superseded`, its calls are hung up, and it is
  closed with `4409`. Previously the newcomer was refused with `agent-in-use`,
  so a forgotten process could hold a slug indefinitely.
- Across instances the Redis lease is claimed unconditionally; an instance
  whose lease was taken closes its connection with `4409` on the next
  heartbeat. An expired lease still closes with `1012`.
- Python raises and Node emits `SessionSupersededError` on `4409`, and neither
  reconnects, so two workers on one slug cannot trade it back and forth.

## SDK 0.3.1 — 2026-09-29

- Retry connection authentication failures three times with fresh realtime
  tokens before the final error. HTTP 401/403 and WebSocket 4401 share the
  budget; only session.ready resets it.
- Preserve capped exponential backoff and one-shot token helpers. Stop
  pending retries when closed, including in-flight token/handshake races.
- Keep standalone Node processes alive until authentication retries finish.
- Add real HTTP/WebSocket and standalone-process regression coverage.
## 2026-09-29

- Local implementation (not released): implemented bounded SDK authentication
  retries for Python and Node connection flows, including fresh-token
  attempts, shared `401`/`403`/`4401` handling, backoff caps, Node `close()`,
  and Python task cancellation.
- Added API-key creation from the API Keys page and permanent deletion of
  revoked keys with tenant checks and audit retention.
- Added multi-select and select-all controls for bulk revocation and deletion
  of revoked API keys.

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

# Project changelog

## Shorter copy action label — 2026-10-21

- Shortened the shared API-key button to **Copy config** and kept its label
  on one line in Partner Apps and API Keys. Copied content is unchanged.

## Partner App logical deletion and persistent key configuration — 2026-10-21

- Added additive migration `0007_partner_app_logical_delete` with nullable
  `partner_apps.deleted_at` and `api_keys.encrypted_secret`. Partner App Delete
  now requires every API-key row to be explicitly revoked, including expired
  keys. An unrevoked key returns `409` with no app, key or audit mutation; after
  the precondition, the app leaves the management dashboard, becomes disabled
  and recoverable ciphertext is cleared, while key rows, call history,
  phone-number references and outbound assignments remain. Existing active
  calls continue to completion; no hard delete or forced live-session teardown
  was added.
- Added optional `GATEWAY_API_KEY_ENCRYPTION_KEY` Fernet recovery for newly
  issued and deliberately rotated keys. API-key list responses remain
  metadata-only and expose `copy_available`; existing hash-only keys and keys
  issued without the setting require deliberate Issue or Rotate replacement.
  Create and rotate responses retain plaintext `key` for API compatibility,
  while a newly issued hash-only flow may hold it only in ephemeral React state
  until refresh/logout; it is never persisted in browser storage, URLs or logs.
- Added tenant-scoped `POST /api/v1/api-keys/{key_id}/reveal` for eligible
  Owner/Admin/Developer actions with `no-store`/`no-cache` headers. The
  per-app Copy configuration action copies only the three-line
  `GATEWAY_URL` (base URL without `/api/v1`), `GATEWAY_API_KEY` and matching
  `AGENT_SLUG` configuration. Revoked keys can be permanently deleted from
  the app card after confirmation; Copy configuration never rotates a key.
- No SDK release or partner protocol change was made. Deployment, migration
  and runtime proof are recorded below as bounded evidence for this feature.
- Added Partner App display-name editing on the dashboard card. **Edit name**
  offers **Save** and **Cancel**; the existing tenant-scoped PATCH trims the
  value and accepts 1–120 characters after trimming, while preserving
  `agent_slug`, API keys and routing/history references.
- Isolated-restore evidence preserved 46 apps, 78 keys, 4 numbers, 4 outbound
  grants, 1,036 calls and 663 signals with identical common-column values and
  digests. The [bounded name-editing tester report](../plans/reports/tester-20261021-app-name-patch.md)
  records `254` repository tests, `24` Node SDK tests and a passing Admin UI
  build, including the name contract checks. PostgreSQL row-lock races were
  verified separately in the final bounded proof below.
- Final bounded live proof used API image
  `3b7ade64cb1fd6bbd484331369bf1d4addf6277d921fb1595446f452951ef759` and UI
  image `c53ffb9a55f545f945a006c39772bb8faf9c46b2a869355360bd6d5dd534bfb9`
  at `http://118.107.77.136:15173`. Isolated PostgreSQL rotation and
  delete/issue race checks passed with the expected `201`/`409` and `204`/`404`
  outcomes. Live API and UI checks covered encrypted recovery, metadata-only
  lists, no-store reveal headers, auth/rotation, explicit revoke-before-delete,
  idempotent deletion,
  hidden/rejected updates, name edit/save/cancel/validation/reload, preserved
  slug, and native Copy output without rendering the plaintext key. Existing
  phone-number assignments and the 1,036 CallRecord / 663 CallSignal digests
  were unchanged; cleanup ended with zero calls/connections and healthy ARI
  plus AudioSocket. Owned fixtures were cleaned without revoking existing
  active keys. This bounded proof does not establish carrier/PSTN coverage or
  a general network/media SLO.

## Admin selection and ordering — 2026-10-21

- Partner Apps displays the newest apps first by creation time, including
  after creating an app or refreshing the page.

## Shared outbound caller-number routing — 2026-10-21

- Added additive migration `0006_outbound_phone_apps` for many outbound
  Partner App assignments per exact number while retaining one inbound Partner
  App owner. The Call Routing UI is at `/call-routing`; `/phone-numbers`
  remains a compatibility route. Phone-number responses expose
  `outbound_partner_apps` and `outbound_partner_app_ids`; PATCH omission
  preserves assignments and an empty list clears them.
- Outbound selection now preserves native default behavior with no assignments,
  selects one eligible enabled number automatically, requires exact
  `caller_number` when multiple eligible numbers exist, and rejects
  assignments with no eligible enabled number. Same-organization ownership,
  `calls:originate`, and destination allowlists remain enforced. Assignment
  changes are local for new calls and do not trigger a PBX reload.
- Added source-level Python `caller_number` and Node `callerNumber` options for
  the wire field `caller_number` without a package release or version bump.
  Published SDK `0.4.0` clients continue to work automatically when one
  eligible number is configured. Bounded native FreePBX, caller-ID and carrier
  signaling evidence is recorded in the dated validation entry below; no SDK
  package release was made.

## Shared outbound live validation — 2026-10-21

- The deployed API reached migration head `0006_outbound_phone_apps`. Focused
  routing/migration/runtime/SDK validation passed (`61` tests), full repository
  validation passed (`234` tests), Node SDK tests passed (`24`), and the Admin
  UI production build passed. No network settings changed; the later native
  repair deployment changed only `res_audiosocket.so` while keeping the
  Asterisk `21.10.2` core unchanged.
- Native FreePBX's deployed `macro-outbound-callerid` consumed
  `__TRUNKCIDOVERRIDE` and preserved the selected caller ID through the local
  macro path. Four internal DID probes reached the expected apps with PCM;
  eight internal outbound probes (two apps on each of four numbers) selected
  the assigned caller ID and delivered PCM to `*43`.
- Before the native repair, four carrier-owned number loops all showed
  signaling up, the expected inbound app, and exact inbound caller identity. In
  the final four outbound loops,
  two carried PCM and two ended with `CallRecord.answered=true` and
  `reason=media_failed` within 0.1 seconds. The PBX logged
  `res_audiosocket.c EAGAIN` (`Resource temporarily unavailable`) before
  destroying AudioSocket on those failures. Passing calls used native PJSIP
  transmit/receive with 50 frames and zero packet loss.
- This pre-repair result is bounded caller-ID/signaling and internal media
  evidence. It does not claim that all PSTN calls passed.

## Native AudioSocket repair deployment — 2026-10-21

- Deployed the matching-version header-read repair as derived image
  `sha256:a3d9f8612a88d8bcc9f4469f06a5ea3c6cf8bc79cd7feaf53e7f5ff796874e23`.
  Asterisk remains `21.10.2`; only `res_audiosocket.so` changed, with module
  hash `sha256:bf41d5a079e28f9827527b29908080004ffa390532f9fad753ae477820946b0f`.
  Compose changed only the `freepbx` service image, using the restricted backup
  at `/opt/asterisk-ai-agent-gateway/backups/audiosocket-20261021T1100/`.
- ABI, symbol and libc checks passed; all three AudioSocket modules loaded in
  an isolated process; and baseline/patched C regressions passed on macOS and
  Linux. No Asterisk core upgrade, network-setting change, or SDK release was
  made.
- Five four-number SIP batches (20 calls) then observed non-silent PCM in both
  directions, with no AudioSocket errors after `11:14:24 UTC`. The final batch's
  two-second, 100-frame check completed for all four calls: all eight native
  legs sent 100 frames, seven received 100 and one received 99, and all
  reported zero transmit and receive packet loss. An earlier strict 50-frame
  receive threshold measured 49 despite PCM in both directions; this is a
  measurement-limit observation, not a silence result or an all-20
  strict-counter pass claim.
- The full internal four-DID and eight shared-outbound set passed, and cleanup
  left zero Gateway calls/connections and zero native channels while preserving
  the four outbound grants and original inbound mappings. Final database proof
  found 61 terminal records and zero `CallRecord` rows with `media_failed`.
- A bounded external-handset listening check covered all four source calls:
  all answered, and non-silent handset voice audio was observed by the Gateway
  across attempts. The immediate two-second tone was not heard. A delayed
  Gateway tone was confirmed clear on all four calls, and one diagnostic call
  also confirmed the native prompt. One busy first attempt required a retry.
  Handset-displayed Caller ID was not confirmed, and no NAT or network setting
  changed. The bounded handset evidence is complete; coverage of every network
  path and an end-to-end PSTN media SLO remain unverified.

## SIP trunks and exact phone-number routing — 2026-10-21

- The Add phone number form now offers unassigned numeric Outbound Caller IDs
  from SIP trunks, with exact-value selection and a prefilled label. Manual
  entry remains available for other inbound DIDs; selecting a number does not
  change FreePBX's global DID matching.
- Added Owner/Admin-only SIP trunk and phone-number management for the
  organization explicitly bound by `FREEPBX_OPERATOR_ORGANIZATION_ID`, backed
  by the private, source-restricted FreePBX BMO bridge. The supported trunk
  surface covers common PJSIP fields, preserves unspecified settings and
  redacts SIP passwords.
- Added additive migration `0005_phone_numbers` for globally unique exact DID
  strings, local Partner App ownership, enabled state and PBX-apply state.
  Managed inbound routing preserves nonempty `AI_GATEWAY_AGENT` precedence;
  otherwise `AI_GATEWAY_DID` resolves an enabled, applied mapping and its owned
  live connection. Inbound routing and existing SDK calls remain compatible;
  shared outbound caller-number selection is recorded in the dated entry above.
- Save and Apply are separate. The fixed native FreePBX reload is guarded by
  zero active calls and exact DID/dialplan/Asterisk readback before a route is
  marked applied. Mapping reassignment is local for new calls and needs no
  reload; FreePBX-backed trunk/DID route changes remain pending until explicit
  Apply.
- Deployed and verified on the pilot: 214 tests, native bridge checks, isolated
  migration, internal DID routing and reassignment, binary media, disabled-call
  rejection, browser saves and Apply. Original trunk settings were preserved
  and temporary trunk/DID fixtures removed. See the [completed rollout](plans/completed/20261021-sip-trunks-and-phone-number-routing.md)
  and the shared outbound live-validation entry above for current runtime
  boundaries.

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

## CMS call-history destination details — 2026-10-20

- Added nullable `called_number` and `routing_context` metadata for the
  authenticated browser call-history detail view. New outbound records capture
  validated destination inputs; inbound records use only supplied dialplan
  destination metadata.
- Kept partner GET/list/signals responses, realtime messages, and SDK contracts
  unchanged. Imported rows and older records remain null unless a
  restricted backup-and-log review proves an exact UUID plus
  `Local/<extension>@<context>` correlation; no heuristic ownership or number
  inference is allowed.
- Deployed API/UI with migration `0004` after a restricted PostgreSQL backup,
  isolated restore/migration rehearsal, and zero active call/media checks.
  Backfilled 61 owned, ended Gateway calls from exact log correlations;
  the second pass updated zero rows and imported destinations remain null.
- Validation: 198 Python tests, 21 Node SDK tests, Ruff, protocol checks and
  UI builds passed. Two isolated live reject/no-answer calls verified new
  destination persistence, CMS detail reads and unchanged partner responses.
  The existing customer connection reconnected after restart. Browser UI
  inspection was unavailable in this session; served assets and authenticated
  detail responses were checked. See the [rollout record](plans/completed/20261020-call-history-destination-details.md).

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

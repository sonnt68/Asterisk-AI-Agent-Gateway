# Execution Plan: CMS Call History Destination Details

Date: 2026-10-20

## Status

Complete: implemented and deployed; interactive browser inspection unavailable.

## Outcome

Add called-number and routing-context metadata to the CMS call-history detail
modal. New Gateway records capture validated destination metadata; old records
remain explicitly unrecorded unless an exact, post-backup PBX-log correlation
proves the Gateway UUID and `Local/<extension>@<context>` endpoint. Partner
GET/list/signals responses and realtime messages remain byte-compatible.

## Context

- Existing durable history and scoped APIs: [completed plan](../completed/20261020-durable-call-history.md).
- Lifecycle ownership/capture: `apps/control-api/app/realtime_registry.py`,
  `outbound_calls.py`, `call_lifecycle.py`.
- Persistence/API: `models.py`, `call_history_store.py`,
  `call_history_schemas.py`, `call_history_routes.py`.
- CMS detail: `apps/admin-ui/src/components/call-history/CallHistoryDetail.tsx`.
- Deployment/rollback: `docs/operations/deployment.md` and
  `docs/operations/backup-restore.md`.
- Completed snapshot investigation: `dd9440e6...` had provider 200 OK at
  07:00:04 UTC before Gateway/answer; no SDK misclassification is evidenced.
  Isolated reject/no-answer rechecks both passed on the deployed Gateway.

## Scope

In scope:

- Add nullable `called_number` and `routing_context` to `CallRecord` and
  `ActiveCall`; add additive migration `0004` after `0003_call_history`.
- Capture outbound validated `extension`/`context` before `persist_start()`.
- Capture inbound only from the supplied `channel.dialplan.exten` and
  `channel.dialplan.context`; do not add an ARI lookup or caller recording.
- Carry fields through the history writer and expose them only from a new
  browser detail response subclass on `GET /call-history/{call_id}`.
- Render Called number/destination, Routing context, and Partner app ID in the
  CMS modal; show `Not recorded` for null or legacy values.
- Backfill only exact UUID `appArgs` to `Local` endpoint matches in PBX logs,
  after backup. Leave source-imported records null; never guess by time,
  number, ownership, or status.
- Test persistence, migration, browser detail isolation, unchanged partner
  contracts, UI build/modal behavior, and the snapshot investigation.

Out of scope:

- Any public partner schema, SDK, realtime frame, list response, or signal
  response change.
- Caller number/audio/transcript storage, CDR ownership inference, or a new
  Asterisk query path.
- Broad legacy import or status correction.

## Approach

1. Add nullable `String(80)` model fields and migration `0004`; preserve nulls
   for existing rows and keep the downgrade additive/recoverable.
2. Extend `ActiveCall`, `_RecordPayload`, start/update/insert paths, and the
   outbound/inbound lifecycle capture points. Validate and length-bound values
   at the capture boundary; missing dialplan metadata stays null.
3. Add a browser-only detail schema inheriting the existing history fields.
   Keep partner routes on `CallHistoryItem`; make the browser detail route use
   the subclass while retaining organization/session isolation and imported
   history rules.
4. Extend the CMS detail type/modal with explicit missing-value copy and keep
   existing loading, signals, focus, Escape, and retry behavior.
5. Run focused tests, migration/tenant/contract checks, and the admin build.
   Re-run the isolated reject/no-answer probe and record whether the
   `dd9440e6...` hypothesis changes; do not alter persisted statuses without
   new correlated evidence.
6. Back up PostgreSQL, source logs, and matching images; migrate and deploy
   API/UI only after active calls/channels/media are zero. Snapshot idle partner
   connections and verify their SDK reconnect after an API restart. Verify
   health, migration head, browser detail, partner contract, and exact old-row
   backfill counts. Roll back with the matching prior image and database backup
   if any check fails; never downgrade under active writers.

## Validation

- Focused: store/model tests prove outbound and inbound metadata persistence,
  null handling, record updates, and imported rows staying null.
- Contract/security: migration head and nullable-column upgrade; browser detail
  exposes the two fields while partner list/detail/signals/realtime payloads
  remain unchanged; cross-tenant detail remains generic `404`.
- UI: `npm --prefix apps/admin-ui run build`; live CMS modal verifies new
  outbound/inbound records, `Partner app ID`, and `Not recorded` for old and
  imported records without regressing modal accessibility.
- Operational: backup is non-empty and mode `0600`; exact UUID-to-Local
  backfill is idempotent and reports zero heuristic updates; health/ARI and
  migration head pass; active calls/channels/media are zero before and after
  API restart; idle partner sessions can reconnect; rollback procedure is ready
  and the backup/migration is tested in isolation.

## Risks And Recovery

- A missing or malformed dialplan block yields null metadata; do not query ARI
  or persist caller data to compensate.
- Existing imported/legacy rows can be summarized but cannot be safely assigned;
  keep them `Not recorded` and source-imported.
- Restore the pre-deploy PostgreSQL backup and matching API/UI images after
  stopping writers if migration or live validation fails. Preserve backfill
  evidence and do not run a live downgrade.

## Progress

- [x] Confirm clean baseline and exact snapshot investigation evidence.
- [x] Implement model, migration, capture, browser schema, and CMS detail.
- [x] Pass focused/repository/UI-build/live API validation; record browser limitation.
- [x] Back up, deploy safely, perform exact backfill, and record rollback proof.

## Delivery evidence

- Full validation: `bash scripts/validate.sh` passed, including 198 Python
  tests, Ruff, protocol parsing, admin build and legacy SDK build.
  `npm --prefix sdks/node test`: 21 passed. Independent review found no
  actionable defects. Four existing aiohttp BasicAuth warnings remain.
- Restricted backup on the operator host:
  `/opt/asterisk-ai-agent-gateway/backups/call-destination-20261020T0732/`.
  `database.sql` is 232355 bytes, mode 0600; source and previous image records
  were saved alongside it. Restored all 840 records to an isolated PostgreSQL
  database, upgraded to `0004`, verified both columns nullable VARCHAR(80),
  then removed only the owned rehearsal database. SQLite upgrade/downgrade
  also passed independently. No live downgrade or restore was performed.
- Before restart: Gateway calls, PBX channels/calls, AudioSocket connections
  and audio queue depth were zero. One idle `ava-voice-agent` connection was
  recorded and reconnected after the API/UI restart.
- Current API image:
  `sha256:e8f6195b02c35cdc6a86c6d95f602f996b5be14b8f625dc48c6cc377b8d0b259`.
  Current UI image:
  `sha256:899dbc41c29ccb626b9b46f774abde1a9f6c65d7942d66f526bb895d3a53f320`.
  Previous API/UI images remain recorded in `images-before.txt` for rollback.
- Exact log scan found 166 distinct UUID-to-endpoint mappings, zero conflicts;
  61 matched owned, ended Gateway outbound records and were backfilled.
  Second pass changed zero rows; imported destination count remained zero.
  The reported `dd9440e6...` record now has its exact called destination.
  Raw mappings and request evidence remain mode 0600 on the operator host.
- Authenticated reads through the admin proxy verified the target call's new
  detail fields, legacy nulls, unchanged list responses, and healthy runtime.
  Served UI assets contain the new detail fields and fallback copy. Interactive
  browser inspection could not run: the selected browser had no tabs and its
  backend does not support tab/window creation. No visual modal pass is claimed.
- Post-deploy isolated live calls:
  `acb93779-4c21-496e-876b-02450936b0dc`: dialing -> rejected, cause 21;
  `f09c5a03-4349-45b4-ba2c-768842a5fc29`: dialing -> ringing -> no_answer.
  Both persisted the exact test extension/context, returned these only through
  CMS detail, and retained the partner detail contract. No PSTN numbers called.
  Test keys were revoked, apps disabled, and temporary extensions removed.
  Final active calls/channels/media were zero; ARI and customer session healthy.

## Investigation evidence

- Target UUID: provider INVITE response 200 OK, Queueing ANSWER and provider
  Dial answer at 07:00:04 UTC, before Gateway posted the Local answer command.
  Earlier 183 PROGRESS did not mark the call answered. DB transitions:
  dialing at 06:59:44.831, answered at 07:00:04.838, completed at 07:00:16.770.
- The recorded `reason=completed` and matching ARI DELETE indicate a requested
  hangup/cancel after provider answer. The handset action/voicemail is unknown;
  do not infer a human answer or rewrite status from the customer's intention.
- Deployed isolated proxy probe: reject call `06118e5e-1a71-4ee8-8ece-221b72b49759`
  produced dialing -> rejected, cause 21, no media; ring call
  `ec66c33c-3118-4b23-b133-6769f43e3e24` produced dialing -> ringing -> no_answer,
  cause 0, no media. Final status queries passed, active calls returned to zero.
  Temporary extensions were removed and the probe revoked its key/disabled app.
- Focused local debug tests: 37 signal/outbound cases and 22 control/signal
  cases passed; no answer-semantics changes are warranted by this evidence.

## Unresolved questions

- The customer's handset action and any carrier announcement/voicemail are
  unknown. Provider answer is proven; human answer is not.
- Interactive modal visual/keyboard recheck remains unperformed because of
  the browser limitation above; API behavior and production build passed.

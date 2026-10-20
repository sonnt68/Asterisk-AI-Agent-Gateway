# Durable call history and customer GET APIs

Date: 2026-10-20

## Status

Completed

## Outcome and authority

User authorized durable Gateway call/signals history, customer-scoped GET
list/detail/signals, and internal tracking. User asked to reuse existing source
history and confirmed legacy records must be CMS-only, not customer-readable.
Customer documentation uses Gateway terminology; keep real SDK identifiers.

## Source evidence

- Live source: 1,882 CDR rows, 779 linked groups, 2026-06-27 through 2026-10-20.
  Outcomes: ANSWERED 1,707, NO ANSWER 103, BUSY 72 (rows, not unique calls).
- CEL disabled; unanswered/congestion logging disabled. Source cannot recover
  every progress signal. Three source rows can describe one answered call.
- No account/user ownership tags. Outbound `lastdata` sometimes carries the
  Gateway call UUID, but no partner/organization mapping survives historically.
- Read-only export at `/tmp/gateway-cdr-history-source.json`, mode 0600, omits
  caller/destination PII. Source credentials remain on the source host.

## Design and boundaries

- Capture immutable organization/app ownership for new calls; persist status
  transitions with unique call/sequence identity. Keep current WS semantics.
- Store metadata and status evidence, not audio, transcripts or caller numbers.
  Keep history without automatic deletion, matching long-term tracking intent.
- Import old summaries idempotently into the current operator organization,
  with no partner app. Do not invent missing timelines or customer ownership.
- Customer `GET /api/v1/partner/calls`, `/{call_id}`, `/{call_id}/signals`:
  Bearer API key, active/enabled/unexpired/unrevoked, `calls:read`; filter by
  organization AND partner app. Unknown/non-owned call IDs return generic 404.
- Both canonical SDKs expose direct authenticated GET helpers without opening
  realtime. Node: listCalls/getCall/listCallSignals. Python:
  list_calls/get_call/list_call_signals. Build 0.4.0 is supplied as installable
  wheel/tarball; public npm/PyPI remain 0.3.2 pending separate publication.
- Browser `GET /api/v1/call-history` and matching detail/signals use existing
  organization sessions. Only owner/admin may see unassigned imported history.
- List response `{items, next_cursor}`; default 50/max 100; stable descending
  created-at/UUID cursor; filters status/direction/start time. Signals ascend by
  sequence with bounded pagination. Current `/calls` active view stays intact.
- User follow-up: exact `agent_slug` filter and optional `page` mode with
  `page_size`, `total`, `total_pages`; keep cursor mode compatible. Page and
  cursor are mutually exclusive. CMS uses a scoped historic-agent selector,
  numbered page navigation and a modal for View, with keyboard/focus support.
- Call shape: call_id, partner_app_id, agent_slug, direction, source,
  status, terminal, answered, reason, hangup_cause, dial_status, sequence,
  created_at, updated_at, answered_at, ended_at, duration_seconds,
  talk_seconds, history_complete. Imported history is summary-only.

## Approach and ownership

1. Persistence agent: models, migration, history writer/import parser and
   lifecycle capture. Root: authentication/query routes and app wiring.
2. UI agent: Calls page with history/detail/signal views and existing live view.
3. Tester: persistence, isolation, pagination, import, restart and failures.
4. Documentation and independent review; full native validation.
5. Back up source/images/PostgreSQL, migrate/deploy, import legacy summaries,
   verify real calls, REST ownership and CMS, then clean up probe resources.

## Risks and recovery

- No speculative matching by phone/time. Legacy data remains internal.
- Database failure must be observable and must not silently break live audio;
  inspect implementation/failure proof before deployment.
- Migration is additive. Back up PostgreSQL and running images before deploy;
  restore matching database/image on failed validation, never downgrade live.
- Preserve dirty changes from earlier call-signals and customer-doc tasks.

## Progress and proof

- [x] Inspect repository and live source; planner recommendation received.
- [x] Fetch sanitized source summaries; user confirmed internal-only import.
- [x] Implement persistence, APIs, CMS, SDK GET helpers and migration.
- [x] Validate focused/full gates, documentation and independent review.
- [x] Deploy, import and verify live persistence/access isolation/UI.
- [x] Implement and verify follow-up agent filter, numbered pages and detail modal.

Local proof: final `bash scripts/validate.sh` passed 194 pytest tests, Ruff,
schema checks, CMS/legacy SDK builds; canonical Node SDK 21 tests. Four existing
aiohttp BasicAuth deprecation warnings remain. Typed cursors, probe-file
permissions, agent isolation, filtered totals and direct page jumps have
regression proof. Independent review has no remaining findings. Customer
docs/contracts: 19 tests; skill build and quick validation passed. Final fresh
npm/wheel installs passed real loopback GET checks (Python 3 tests), signatures,
types, package contents and README equality.

Operational preflight: root-only source/image/PostgreSQL backups at
`/opt/asterisk-ai-agent-gateway/backups/20261020-call-history/`. Restored backup
into an isolated PostgreSQL database, migrated 0002 to 0003 and proved real
CallRecord/CallSignal foreign-key writes; removed the disposable database.
Packaging initially copied macOS metadata as `._*.py`; the isolated migration
check caught this before production deployment. Removed those archive metadata
files and rebuilt; no production schema was changed during the failed check.

## Result

- Deployed API/UI on `118.107.77.136`, migration head `0003_call_history`.
  Final image IDs: API `219b50f682c000851588802ee5b240b8ab1708bae2ee5f0926a1acd2ab2767a6`,
  UI `6a4f439da35e85eefa84c5744cd6d030e7a9b3e0e97c650e5048ce94326e6f66`.
- Imported 779 summaries with no partner ownership. Second import inserted 0.
  Live database contains 779 imported summaries and 15 Gateway probe calls.
- Python and Node SDKs read 8 real calls, details and ascending signals; another
  app received empty lists/generic 404. Calls remained byte-identical after
  API-container recreation. Final rebuilt Python wheel also passed live agent
  filters, page 1/page 3 (8 calls, page size 3), totals, detail/signals,
  empty foreign-agent results and mixed-mode 422.
- CMS proof in Chrome: historic-agent selector returned exactly 8 calls for
  the selected test agent; reset restored 794 calls across 16 pages; direct
  jump to page 16 showed rows 751–794 from June. View opened a centered,
  independently scrolling modal with full metadata and dialing/answered/
  completed timeline. Imported records showed summary-only copy. Tab trapping,
  Escape close, focus restoration, body scroll lock and Home/End tab navigation
  passed through the actual UI.
- Rebuilt direct SDK 0.4.0 artifacts served under
  `http://118.107.77.136:15173/downloads/sdk-0.4.0/`; downloads byte-match local
  packages. SHA256: npm `65cd314bfbc97a2e762f8d9064cc1fe1ebff0f93c5a6a9e460215fdd9eecfd43`,
  wheel `390ce1d2f0ba6e8aa9cc221b0251440e956c105067f107b4fa1ad4a6995c1c2c`,
  sdist `d0e3c71f1832344e4e75caefbeb1f243b9aa75a7c8a32fea4733f2847bf3e511`.
- Revoked all temporary keys (401 verified), disabled test apps, removed six
  temporary dialplan extensions and credential state files, and uninstalled
  temporary SDK from the API container. Final active calls/channels/media/
  partner connections 0; ARI connected 1. Retained call audit/history as intended.

Limitation: the first answered probe hit AudioSocket header-read EAGAIN on
Asterisk 21.10.2. The identical subsequent eight-scenario run passed without
media changes. Read-only diagnosis found no Gateway media-code or DB error;
durable-write timing may affect exposure but causation is unproven. This race
is not fixed by this delivery. No carrier/PSTN call verification.

No commit/push or public npm/PyPI publication requested/performed. Source calls
outside Gateway need a later manual import; no unrestricted source poller.

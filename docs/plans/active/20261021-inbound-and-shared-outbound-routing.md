# Execution Plan: Inbound And Shared Outbound Routing

Date: 2026-10-21

## Status

Feature deployed; native AudioSocket repair authorized by the user ("Sửa đi").
Repair and repeated four-number validation in progress; keep active for recovery.

## Outcome

Keep one exact DID mapped to exactly one inbound Partner App while allowing
multiple same-organization Partner Apps to use that DID as an outbound caller
number. Outbound origination chooses an assigned enabled number explicitly or
deterministically, preserves the existing dialplan behavior for apps with no
assignment, and never selects an arbitrary database row. The Admin UI calls the
existing phone-number page **Call Routing**, labels inbound and outbound
directions separately, and keeps the existing number picker.

## Context

- Authority and workflow: [README](../../../README.md),
  [AGENTS](../../../AGENTS.md), [workflow](../../WORKFLOW.md), and
  [encoding invariants](../../patterns/encoding-invariants.md).
- Existing telephony behavior: [SIP trunks and phone numbers](../../operations/sip-trunks-and-phone-numbers.md),
  `apps/control-api/app/models.py`, `phone_number_routes.py`,
  `telephony_schemas.py`, `telephony.py`, and `outbound_calls.py`.
- Existing partner contract: `packages/protocol/asyncapi.yaml`,
  `sdks/python/asterisk_ai_gateway/client.py`,
  `sdks/node/src/index.js`, and `sdks/node/types/index.d.ts`.
- Existing Admin UI surfaces: `apps/admin-ui/src/telephony/`, `App.tsx`,
  `components/layout/Sidebar.tsx`, and `components/layout/Header.tsx`.
- Native evidence: Asterisk 21 ARI `POST /channels` supports `callerId`, while
  the deployed FreePBX `macro-dialout-trunk` calls
  `macro-outbound-callerid`, which can replace it with the trunk `OUTCID`.
  Native caller-ID retention is therefore a deployment validation dependency,
  not an assumed carrier result.

## Work Ownership

- Backend agent: migration, `PhoneNumberOutboundApp` model, management API,
  same-org selection, and outbound runtime behavior.
- Frontend agent: Call Routing labels, direction-specific assignment controls,
  number picker retention, and browser proof.
- Root: AsyncAPI/canonical SDK source changes, native caller-ID probe, backup,
  live internal validation, deployment, and final integration.

## Scope

In scope:

- Preserve `phone_numbers.number` global exact uniqueness and required inbound
  `partner_app_id`. No inbound load balancing and no automatic backfill of
  outbound grants.
- Add migration/model table `phone_number_outbound_apps` with a composite
  `(phone_number_id, partner_app_id)` key, tenant-safe foreign keys/indexes,
  and an empty initial state. One app may have many numbers; one number may be
  assigned to many apps for outbound caller ID.
- Add Owner/Admin, deployment-bound operator-organization checks to outbound
  assignment CRUD. New assignments require an enabled same-organization app;
  existing assignments remain visible when an app or number is later disabled,
  but disabled rows are never eligible for new calls and are not deleted by an
  unrelated edit.
- Extend phone-number management responses with separate inbound app data and
  outbound assigned-app data. Extend existing create/update endpoints with
  `outbound_partner_app_ids` (omit to preserve, empty list to clear), and audit
  assignment changes; retain the current inbound create/update semantics.
- Resolve outbound caller ID from the authenticated connection's exact
  organization and Partner App:
  - zero assignment rows: preserve the current `Local/<extension>@<context>/n`
    originate shape and omit caller-ID configuration;
  - exactly one eligible enabled number: use it automatically;
  - multiple eligible numbers: require optional wire field `caller_number`;
  - an explicit value must exactly match an eligible assignment or the request
    is rejected; zero eligible rows with stale/disabled assignments also reject
    rather than silently falling back.
- Pass the selected exact number through the verified FreePBX/Asterisk caller-ID
  mechanism. Keep the selected number out of durable call history unless an
  existing public contract explicitly requires it.
- Add optional `caller_number` to AsyncAPI and backwards-compatible optional
  `caller_number`/`callerNumber` support in the canonical Python and Node SDK
  source. Do not bump versions, publish packages, or release SDK artifacts.
- Rename navigation, page title, description, and breadcrumb to **Call Routing**;
  keep `/phone-numbers` as a compatible URL (an alias may be added only if it
  does not duplicate data loading). Show inbound one-app and outbound many-app
  controls as distinct directions. Retain SIP-trunk number picker behavior.

Out of scope:

- Inbound fan-out/load balancing, a second inbound Partner App on one DID, or
  any change to legacy nonempty `AI_GATEWAY_AGENT` routing.
- Quotas, priority/round-robin defaults, arbitrary caller-ID rewriting,
  provider/carrier enforcement or DID purchase/porting. The user later authorized
  bounded call tests through the four existing numbers; this adds validation,
  not broad native PBX upgrades or network changes. The subsequent explicit
  repair request authorizes a bounded matching-version AudioSocket module fix.
- Trunk association on a phone number, trunk deletion, Docker/host control,
  raw SQL/generic PBX commands, or public partner REST changes.
- SDK package release, version/tag changes, or changes to the older
  `packages/*-sdk` prototypes.

## Approach

1. Add `0006_outbound_phone_apps` after the deployed `0005_phone_numbers`
   migration. Model the composite association, indexes, same-org validation,
   and no-backfill upgrade path; rehearse fresh and upgrade migrations.
2. Add strict schemas to the existing typed management routes for listing and
   replacing assignments. Serialize both
   directions, audit mutations, reject cross-tenant IDs and non-manager roles,
   and keep inbound `partner_app_id` updates independent.
3. Add a small outbound selection helper used by `outbound_calls.py`. Query by
   the authenticated connection's organization and app, filter enabled rows,
   distinguish no grants from unusable grants, reject ambiguity, and validate
   exact `caller_number` before reserving a call or making an ARI request.
4. Extend the ARI originate parameters with the selected caller ID only after
   the native probe confirms how FreePBX propagates it. If `callerId` is
   overridden, use the narrowest existing FreePBX custom hook/variable path
   supported by the deployment and prove it with readback; do not claim carrier
   acceptance from an ARI HTTP success.
5. Update AsyncAPI and canonical SDK source/tests so old calls serialize exactly
   as before and the optional field is sent only when supplied. No release or
   partner migration is part of this plan.
6. Update Call Routing UI types, hook, page, form, table, nav, and breadcrumb.
   Render the inbound app as one value and outbound apps as a real editable
   list with disabled/unavailable states, explicit ambiguity errors, and no
   fake per-trunk assignment. Keep the current exact number picker.
7. Update the owning operations text after behavior is verified, then run the
   isolated migration, API/runtime, SDK/protocol, browser, and live internal
   probe gates before any requested deployment.

## Risks And Recovery

- A cross-tenant assignment could expose a DID: enforce organization equality
  in every API query and runtime join, and prove both allowed and denied cases.
- A disabled or removed assignment could silently fall back to an unintended
  caller ID: reject when grants exist but none are eligible; preserve fallback
  only when the app has no assignment rows at all.
- Multiple eligible numbers could produce nondeterministic caller ID: require
  the explicit exact `caller_number` and reject ambiguity before ARI side
  effects.
- FreePBX may override ARI `callerId` with trunk `OUTCID`: use the native
  internal probe and preserve a deployment blocker/rollback path if the narrow
  hook cannot be proven. Never report carrier/PSTN success from local evidence.
- Migration or assignment writes could leave partial state: use a restricted
  database backup, isolated restore/rehearsal, transactional association CRUD,
  exact fixture cleanup, and restore the matching image/database rather than a
  live downgrade.
- UI terminology could hide direction semantics: make inbound and outbound
  labels visible in the same row/form and browser-test both assignment paths.

## Progress

- [x] Reconfirm current `0005_phone_numbers` schema and capture migration backup.
- [x] Add and test `phone_number_outbound_apps` migration/model with no backfill.
- [x] Implement assignment schemas/routes/serialization/audit and same-org RBAC.
- [x] Implement zero/one/multiple outbound caller selection and ARI integration.
- [x] Run native FreePBX caller-ID propagation probe and record the result.
- [x] Update AsyncAPI and canonical SDK source/tests without releasing packages.
- [x] Rename UI surfaces to Call Routing and add real direction-specific controls.
- [x] Run API/runtime, migration, protocol/SDK, browser, and live internal tests.
- [x] Complete backup, rollout, readback, and rollback evidence before deployment.
- [x] Execute the user-authorized four-number SIP loop tests and report failures.
- [ ] Resolve the native Asterisk AudioSocket failure before claiming stable end-to-end media.

## Decisions

- 2026-10-21: `PhoneNumber.partner_app_id` remains the sole inbound owner;
  outbound sharing is an additive many-to-many association with no automatic
  grants for existing rows.
- 2026-10-21: Outbound eligibility requires the exact same organization,
  enabled Partner App, and enabled PhoneNumber. Disabled associations remain
  stored for later recovery but are unusable for new calls.
- 2026-10-21: No outbound grants preserve current originate behavior; exactly
  one eligible grant auto-selects; multiple eligible grants require exact
  optional `caller_number`; ambiguity and unusable grants fail closed.
- 2026-10-21: Wire field is optional `caller_number`; canonical SDKs expose
  backwards-compatible idiomatic options, with no SDK release requested.
- 2026-10-21: Display name changes to Call Routing while `/phone-numbers`
  remains compatible. Inbound and outbound directions must be visibly distinct.

## Validation

- Focused backend proof: fresh/upgrade migration, composite uniqueness,
  no-backfill state, owner/admin operator binding, same-org checks, disabled
  assignment behavior, add/remove audit, and exact response serialization.
- Runtime proof: no-grant legacy ARI shape, one-grant automatic `callerId`,
  explicit exact match, ambiguous/missing/disabled rejection, cross-org
  rejection, no reserved call or ARI request on selection failure, and no
  change to inbound legacy precedence.
- Protocol/SDK proof: AsyncAPI schema accepts optional field; Python and Node
  canonical SDK tests prove omitted and supplied payloads; existing calls and
  SDK builds remain compatible. No package publication is claimed.
- UI proof: browser checks Call Routing nav/title/breadcrumb, inbound single-app
  editing, outbound multi-app add/remove, disabled labels, ambiguity errors,
  number picker retention, and old URL compatibility.
- Deployment proof: restricted DB backup, isolated migration restore, native
  FreePBX/Asterisk internal probe with no carrier dial, zero active calls,
  exact caller-ID/channel evidence, cleanup, health, and rollback readiness.

## Result

Deployed API migration `0006_outbound_phone_apps` and Call Routing UI on
2026-10-21. Existing four inbound mappings, enabled/applied state and user app
settings preserved. No outbound grants were backfilled; temporary test grants
were removed after probes. No SDK publication, native configuration reload,
Asterisk binary replacement, commit or push was performed.

- Local validation: focused Python 61 passed; full `scripts/validate.sh` 234
  passed; canonical Node SDK 24 passed; Admin UI production build passed.
  Reviewer copy mismatch fixed: existing inbound reassignment is immediate,
  only newly added native routes await Apply. Browser confirmed legacy URL
  redirect, Call Routing nav/title/breadcrumb, and multiple outbound selections.
- Recovery: restricted backup
  `/opt/asterisk-ai-agent-gateway/backups/shared-routing-20261021T1003/`
  contains pre-migration DB/source/images. Isolated PostgreSQL restore upgraded
  0005 to 0006 with all table row counts and four inbound mappings preserved,
  zero grants, and composite uniqueness/foreign-key negative proof; rehearsal
  DB removed. Prior images tagged `gateway-api:before-shared-routing-20261021`
  and `gateway-admin-ui:before-shared-routing-20261021`.
- Running image IDs: API
  `sha256:c6708e7b72716fc4fb7b9bba260bf46130dfa9d6cc3cac5c212ed2d445fedf38`;
  admin UI
  `sha256:00ca7b5018847f85f0bacf19bb5b2113650cb1b255723e21a73911e1cd54816f`.
- Native Local-only macro probe confirmed the inherited
  `__TRUNKCIDOVERRIDE` preserves the selected exact caller ID across the Local
  pair without native configuration edits.
- Live internal: all four existing DID mappings reached their actual assigned
  app and carried PCM. Both temporary outbound apps used each number, eight
  internal echo calls total, with exact caller ID and PCM.
- Final SIP loop: all four calls answered, reached the correct inbound app,
  and presented the selected exact caller ID. Two calls carried non-silent PCM
  both ways, with 50 TX/50 RX packets and zero reported loss on both PJSIP legs;
  two ended as `media_failed` within 0.1–0.2 seconds of answering. Native logs
  correlate those UUIDs with AudioSocket header-read EAGAIN and channel teardown.
  This is intermittent native media failure, not a number-specific routing
  rejection; do not mark these end-to-end tests passed.
- An initial short-beep/silent-peer probe produced media timeouts. Longer
  internal playback and simultaneous active signals improved the test, but
  the final four-call test still reproduced two genuine native failures.
- Cleanup verified: all 24 short-lived test keys revoked, eight fixture apps
  disabled, zero temporary grants, original inbound assignments unchanged,
  zero active calls/connections, ARI and AudioSocket healthy.

See [live report](../../../plans/reports/tester-20261021-live-shared-routing.md)
and [local suite report](../../../plans/reports/tester-20261021-shared-outbound-routing.md).
Raw JSON and screenshots are in `/tmp/gateway-telephony-proof-20261021/` on the
workstation and matching `/tmp/gateway-shared-routing-*.jsonl` on the server.

## Unresolved Questions And Limits

- Native Asterisk 21.10.2 reads the AudioSocket header once and treats EAGAIN
  as fatal; the deployed logs and durable call records match that failure.
  Native repair/backport/upgrade is not implemented or validated. Do not claim
  a specific later release or upstream commit is a tested drop-in repair.
- Four owned numbers called each other through the configured SIP trunk. No
  external handset/mobile-network call or sustained audio quality test occurred.
- Docker does not publish Asterisk's configured RTP range. This is an untested
  external-handset boundary, not the demonstrated cause of these loop failures:
  passing loop calls had bidirectional native RTP counters.
- Actual Partner Apps had no live sessions before/after temporary verification;
  operators must connect their agents for normal inbound service.


## Authorized Native AudioSocket Repair (2026-10-21)

Outcome: eliminate the observed nonblocking header-read EAGAIN teardown on
Asterisk 21.10.2, retain normal PCM/hangup behavior, and repeat every owned-number
SIP loop with bidirectional PCM and native RTP counters. User explicitly
authorized repair after the 2/4 media-failure report. No routing, trunk, RTP
exposure, or SDK policy changes are needed.

- [ ] Inventory exact native build, module ABI and persistent deployment owner.
- [ ] Back up original module, matching image identity and deployment configuration.
- [ ] Implement matching-version bounded idle read and fragmented-header handling.
- [ ] Compile and prove idle EAGAIN, fragmentation, PCM, disconnect and errors.
- [ ] Review native patch and recovery before zero-call module replacement.
- [ ] Persist the replacement across container recreation and verify loaded hash.
- [ ] Repeat all four SIP loops; require all four passing in repeated batches, no
      correlated native header-read errors, exact caller ID and inbound owner.
- [ ] Verify fixture cleanup, zero active calls/connections, unchanged assignments.

Recovery: retain exact original module and image before mutation. Build without
modifying the running process. Before reload/restart, require zero native calls
and no real agent sessions. If module fails to load or focused native probes
regress, restore the original module/deployment configuration and reload only
AudioSocket dependents; avoid a broad FreePBX or host upgrade.

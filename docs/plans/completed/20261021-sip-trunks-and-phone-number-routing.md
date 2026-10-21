# Execution Plan: SIP Trunks And Phone Number Routing

Date: 2026-10-21

## Status

Completed; deployed and verified 2026-10-21 09:32 UTC.

## Outcome

Owner/Admin users of the deployment-bound operator organization can manage the
safe subset of FreePBX PJSIP trunk configuration and map exact phone numbers to
enabled Partner Apps. A private FreePBX BMO bridge applies managed DID routes
only after an explicit apply operation and exact readback. Existing partner
WebSocket/API behavior and legacy `AI_GATEWAY_AGENT` routing remain compatible.

## Context

- Product and constraints: [README](../../../README.md),
  [workflow](../../WORKFLOW.md).
- Architecture and trust boundaries: [architecture](../../architecture.md),
  [security model](../../security-model.md), and
  [Asterisk connection operations](../../operations/asterisk-connection.md).
- Current runtime/API/UI: `apps/control-api/app/call_lifecycle.py`,
  `apps/control-api/app/models.py`, `apps/control-api/app/database.py`,
  `apps/control-api/app/main.py`, `apps/control-api/app/management_routes.py`,
  `apps/control-api/app/auth.py`, `apps/admin-ui/src/pages/AsteriskPage.tsx`,
  `apps/admin-ui/src/pages/PartnerAppsPage.tsx`,
  `apps/admin-ui/src/hooks/useGatewayData.tsx`,
  `apps/admin-ui/src/lib/api.ts`, `apps/admin-ui/src/components/layout/Sidebar.tsx`,
  and `packages/protocol/openapi.yaml`.
- FreePBX17/Asterisk21 evidence: the stock API module is absent and the stock
  trunk GraphQL provider is commented out; active Core/PJSIP BMO methods are the
  supported deployment integration seam. FreePBX separates global inbound DID
  routing from trunk configuration.

## Scope

In scope:

- A private, token- and source-restricted PHP bridge under
  `integrations/freepbx/` using explicit FreePBX BMO actions. No Docker socket,
  arbitrary shell, raw SQL, or generic command/GraphQL proxy.
- Inventory and safe create/edit/disable for PJSIP trunks, including outbound
  authentication and send-registration settings. Preserve unspecified settings
  and existing passwords; never return or log SIP secrets. Trunk deletion is
  excluded.
- Deployment binding through `FREEPBX_OPERATOR_ORGANIZATION_ID`; only Owner and
  Admin of that exact organization may use PBX management endpoints.
- A Gateway `PhoneNumber` table and migration with exact DID uniqueness, DID
  syntax of optional `+` followed by digits, no automatic normalization, org
  and Partner App foreign keys, label, enabled state, and PBX-applied state.
  There is deliberately no Gateway trunk mirror or per-DID trunk foreign key.
- Deterministic managed DID context generation that sets exact
  `AI_GATEWAY_DID`, resolves the local enabled Partner App, and preserves the
  legacy rule that a nonempty `AI_GATEWAY_AGENT` takes precedence.
- Typed, tenant- and role-checked browser APIs, audit coverage, OpenAPI updates,
  and Admin UI SIP Trunks and Phone Numbers routes/forms/statuses.
- Separate local save and PBX Apply Configuration. Apply uses fixed BMO
  `doReload`, rejects active PBX calls, reads back exact managed routes, and
  changes `pbx_applied` only after matching readback. Reassigning an existing
  number to another app is local-only and requires no reload.

Out of scope:

- Carrier/PSTN account provisioning, DID purchase/porting/activation, or live
  carrier call validation; provider credentials and calls were not supplied.
- Public Partner App contract changes, direct partner access to FreePBX, or
  exposing Asterisk credentials/configuration through the Gateway.
- Trunk deletion, automatic DID normalization, per-DID trunk selection, or a
  false tenant-level view of a shared PBX inventory.
- Docker/host management surfaces, arbitrary backend commands, and a Gateway
  database mirror of all FreePBX trunks.

## Approach

1. Define bridge action schemas, deployment-secret loading, source allowlisting,
   redaction, and operator-org configuration. Keep the bridge narrow and
   version-pinned to the FreePBX BMO calls used by this feature.
2. Implement trunk inventory and explicit PJSIP create/edit/disable in the
   bridge, preserving omitted settings/passwords, then implement managed DID
   route generation, fixed reload, and exact route readback.
3. Add the `PhoneNumber` model/migration with global exact DID uniqueness and
   org/app constraints. Keep FreePBX as the trunk/DID source of truth; Gateway
   stores ownership, mapping, and apply state only.
4. Add owner/admin and operator-organization checks to typed management routes;
   validate app ownership/enabled state, audit mutations, keep partner routes
   unchanged, and return pending/applied/reload errors truthfully.
5. Connect inbound lifecycle handling to managed `AI_GATEWAY_DID` resolution,
   fail closed when the mapped app or live connection is unavailable, and
   preserve nonempty legacy `AI_GATEWAY_AGENT` behavior before managed lookup.
6. Add Admin UI navigation, pages, forms, save/apply status, redacted trunk
   fields, and error states; update the OpenAPI protocol contract.
7. Validate in an isolated FreePBX17/Asterisk21 fixture, then prepare backup,
   isolated migration, active-call check, apply/readback, and rollback steps for
   any requested live deployment.

## Risks And Recovery

- Bridge or SIP credentials could leak: keep them in deployment secrets, redact
  responses/logs, use narrow token/source checks, and rotate/revoke the bridge
  secret on incident.
- FreePBX BMO behavior can drift: pin the tested integration, require exact
  readback, and disable the bridge or restore the prior module/config on failure.
- Reloading active calls is unsafe: reject Apply while calls exist and require a
  zero-call preflight for deployment; do not claim a reload succeeded from a
  local HTTP success alone.
- Save/apply can partially fail: leave local state pending until readback
  matches, expose the failure, and make retry/rollback deterministic.
- Shared PBX inventory can cross tenant boundaries: bind every route to the
  configured operator organization and enforce Owner/Admin checks server-side;
  never infer isolation from a DID or trunk label.
- Legacy calls may omit managed metadata: retain the existing custom-context
  path and nonempty `AI_GATEWAY_AGENT` precedence; fail closed when no valid
  route/app exists.

## Progress

- [x] Confirm bridge schemas and deployment-secret/source restrictions.
- [x] Implement and syntax-check the FreePBX BMO bridge.
- [x] Add isolated Gateway migration/model and phone-number constraints.
- [x] Implement tenant/RBAC APIs, audit events, apply/readback, and OpenAPI.
- [x] Implement managed inbound runtime behavior without changing partner routes.
- [x] Implement Admin UI trunk and phone-number pages/navigation.
- [x] Run focused, integration, repository, and browser validation.
- [x] Complete backup/migration/reload/rollback gates before any live deployment.

## Decisions

- 2026-10-21: Full SIP account/configuration management plus DID-to-Partner-App
  mapping is approved; the integration boundary is a private, narrow FreePBX
  BMO bridge because the stock API/GraphQL trunk surface is unavailable.
- 2026-10-21: `FREEPBX_OPERATOR_ORGANIZATION_ID` is the explicit shared-PBX
  authority boundary; only Owner/Admin of that organization may manage it.
- 2026-10-21: Do not mirror trunks in Gateway, delete trunks, or attach a DID
  to a selected trunk; FreePBX inbound DID routing is global in this deployment.
- 2026-10-21: DID values are exact strings matching optional `+` plus digits;
  no normalization is performed. Apply is explicit, reload is guarded, and
  applied state requires exact readback.

## Validation

- Focused proof: migration/model constraints; org, role, app-ownership,
  operator-binding, secret-redaction, audit, pending/apply, active-call reject,
  exact-readback, legacy-precedence, managed-route, reassignment, and fail-
  closed runtime tests.
- Integration proof: PHP syntax checks plus an isolated FreePBX17/Asterisk21
  fixture covering BMO trunk create/edit/disable, managed route generation,
  reload, and exact readback. No carrier or live-call claim without evidence.
- Repository proof: applicable `ruff`/`pytest`, Admin UI build/type checks,
  protocol schema tests, `bash scripts/validate.sh`, and browser verification
  of the new Owner/Admin flows.
- Deployment proof: backup, isolated migration rehearsal, zero active calls,
  apply/readback confirmation, and documented rollback before touching the
  requested live site.

## Result

Deployed API and Admin UI to the requested pilot and verified native FreePBX
management, managed inbound routing, browser saves and Apply.

- `bash scripts/validate.sh`: passed with 214 pytest cases, Ruff, protocol/config
  parsing, shell checks, Admin UI typecheck/build and Node SDK build. Final PHP
  lint and 23 regression checks passed. Final auth/header/parser review passed;
  see [review report](../../../plans/reports/reviewer-20261021-telephony.md).
- Restricted backup: `/opt/asterisk-ai-agent-gateway/backups/telephony-20261021T0903/`
  contains Gateway/PostgreSQL, FreePBX/MariaDB, Asterisk configuration,
  application source/environment, and prior image IDs. Prior images also have
  `gateway-api:before-telephony-20261021` and
  `gateway-admin-ui:before-telephony-20261021` tags.
- Isolated PostgreSQL restore upgraded from `0004_call_destination` to
  `0005_phone_numbers`; all 923 original call records remained, exact-number
  uniqueness and app foreign keys rejected invalid writes, and fixture rollback
  left zero phone numbers. The disposable database was removed after validation.
- Apache compatibility required directory-scoped Authorization forwarding and
  FreePBX's programmatic BMO bootstrap. Authenticated private HTTP returned 200;
  public HTTP returned 403. Source/Bearer checks precede native bootstrap.
- Live additive migration reached `0005_phone_numbers`; health passed. New
  images: API `sha256:96c86f592211e47a3ad3f4edf7696925287d27bf8fa0b1b084e800a6603581cb`,
  UI `sha256:347db45c5977a92deb4d932ff9c8f625416bf990f492d8f507724dfacec3054a`.
- Live probe created one disabled loopback trunk and synthetic DID
  `999999920261021`, verified password preservation, pending/apply readback,
  inbound routing to App A, reassignment to App B without reload, binary audio,
  ended events, disabled-number rejection, and zero remaining channels/media.
  It never dialed a carrier. Results are saved on the host under
  `validation/live-telephony-probe.json` and `validation/final-health-proof.json`.
- Browser verified both pages, disabled-app number recovery, trunk editing with
  a blank password, pending-state display, confirmation and successful Apply.
  Local images are under `/tmp/gateway-telephony-proof-20261021/`; the final
  phone-number page is left open for the user.
- Native fixture trunk/DID and Gateway number were removed. Both fixture apps
  are disabled and both temporary keys revoked. All four original trunks match
  their complete pre-test settings hashes. Existing custom contexts are byte
  equivalent after removing the single new managed include and trailing blank
  lines. Final state: zero phone numbers, four trunks, 925 call records (923
  original plus two internal probes), two original active keys, zero active
  calls/connections, ARI connected, AudioSocket listening, no pending reload.

Recovery uses the restricted backups and matching prior images, rather than
running a downgrade with active writers. Stop new traffic, restore the matching
Gateway database/environment/source and image, restore native FreePBX database
and Asterisk configuration only if their state needs recovery, then verify
native reload, health, ARI, and exact original inventory before reopening.
The test cleanup used only the exact fixture IDs and preserved original state.

## Admin UI Follow-up

The operator requested number selection from existing SIP trunks and newest
Partner Apps first. The UI now offers exact, unassigned numeric Outbound Caller
IDs from the existing inventory, deduplicates identical numbers, prefills a
label, and retains manual entry for other DIDs. This copies a number into the
existing mapping API; it does not create a trunk association. Partner App cards
sort by descending `created_at` and a deterministic ID tie-break.

- TypeScript/Vite production build, diff checks and the bounded UI review passed.
- Deployed only Admin UI image
  `sha256:26f77b9b8d645712b3ca37fe71635c03ee0e9d86149488ae545dd3d870ced1cf`.
  The API retained its verified image. UI asset and API health returned 200.
- Recovery: restricted source backup
  `/opt/asterisk-ai-agent-gateway/backups/admin-selection-20261021T094409/`
  and image tag `gateway-admin-ui:before-admin-selection-20261021`.
- Browser verified all four existing trunk numbers are offered, selecting one
  fills its exact number and label, Partner App selection works, and manual DID
  entry remains available. The draft was cancelled without creating a route.
- Browser showed `vindynamics-3`, `vindynamics-2`, then `vindynamics-1`, matching
  database creation-time order. No app or DID was created by this follow-up.
- Screenshots: `/tmp/gateway-telephony-proof-20261021/select-number-from-trunk.jpg`
  and `/tmp/gateway-telephony-proof-20261021/partner-apps-newest-first.jpg`.

## Unresolved Questions And Limits

- No carrier credentials or new real DID were supplied; provider registration,
  carrier-specific behavior and PSTN inbound/outbound calls remain unverified.
- The requested pilot URL still uses HTTP. Production credential entry needs a
  trusted encrypted path; browser tunnel origins must match deployment origin.
- Apply checks active calls immediately before reload; it does not reserve or
  drain incoming channels during that short interval. Native trunk writes can
  succeed before a later readback fails; inventory and backups support recovery
  without a false successful-apply claim.
- No commit, push, SDK release or carrier account purchase was performed.

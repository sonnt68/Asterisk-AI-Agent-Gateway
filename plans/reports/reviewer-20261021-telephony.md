# Telephony implementation review — 2026-10-21

**Status:** DONE_WITH_CONCERNS

**Scope.** Read-only review of the deployment-bound FreePBX bridge, Gateway
Owner/Admin APIs, managed DID resolver, Admin UI, migration, OpenAPI, and
operator/security docs. Review follows the approved single-PBX scope: the
configured operator organization may manage the complete PBX inventory.

**Validation observed.** The latest repository validation reported by the
parent passed Ruff, `214` pytest cases, protocol/config parsing, shell checks,
the Admin UI production build, and the Node SDK TypeScript build. The bridge
fixture reports `23` checks passed, including source-annotation parsing, and
PHP syntax passes for the bridge and fixture files. The read-only native probe
observed 4 trunks, UDP transports, zero active channels, and
`reload_needed=false`. This reviewer performed no remote mutation.

**Root-run compatibility evidence (reported by root).** An internal bridge
request returned HTTP 200 and a public-source request returned 403. The native
A→B media/disable fixture passed; browser DID/trunk editing and Apply passed;
the original raw-settings hashes for all 4 trunks were unchanged; fixture
DID/trunk/DB-number cleanup passed; calls, media, and connections were 0 with
ARI connected; and the active-key count remained 2. No carrier/PSTN call was
attempted.

## Accepted residuals

### Medium — native trunk post-save readback has a recovery boundary

`integrations/freepbx/trunks.php:45-48` calls `FreepbxBmo::saveTrunk()`, marks
reload pending, and then reads the trunk back. For an existing trunk,
`integrations/freepbx/bmo.php:82-115` deletes and recreates the native PJSIP
trunk and restores the snapshot when the delete/add operation or returned ID
fails. A failure after the native write succeeds, including the later
`bmo->trunk($savedId)` readback, can therefore return an error while the new
native configuration remains on FreePBX. Trunk saves have no `pbx_applied`
claim, so this is not a false local route-applied result.

**Disposition:** accepted recovery boundary under the approved rollout plan.
The restricted backup and follow-up native inventory are the recovery path;
the operator must not interpret a failed response as proof that the prior
native trunk was restored. No automated revert is required by the approved
scope.

### Medium — Apply's zero-channel guard has a count-to-reload window

`integrations/freepbx/dids.php:84-97` checks `activeChannels()` and then
reloads after a separate route readback. The Gateway also rejects when its
in-memory registry is nonempty at `apps/control-api/app/asterisk_routes.py:158-163`.
Neither check reserves Asterisk, so a new channel can begin after the count
and before reload. Existing tests prove rejection when a call is already
visible; they cannot make the check continuous.

**Disposition:** accepted safety boundary. Apply requires zero channels at the
preflight check, and the rollout must disclose that this is not a hard
zero-active-channels guarantee through reload. No drain policy is authorized
in the current scope.

## Targeted fixes verified

- The bridge auth gate is ordered before FreePBX bootstrap. The directory
  `.htaccess` forwards `Authorization` only for the bridge directory
  (`integrations/freepbx/.htaccess:1-4`); `index.php:21-26,35-52` checks POST,
  source CIDR, and bearer token before request parsing or BMO bootstrap; and
  `bmo.php:20-29` sets `freepbx_auth=false` only for that already-authorized
  programmatic BMO load. Root-run HTTP 200/403 results confirm the expected
  header handoff and source gate order.
- Exact native readback is now per extension block. `dids.php:116-121` calls
  `FreepbxGatewayDialplan::hasExactRoute()` for each DID, and
  `dialplan.php:70-115` requires the target extension's contiguous NoOp, exact
  `AI_GATEWAY_DID`, Gateway Stasis application, and Hangup steps. It strips
  trailing FreePBX source annotations before applying those exact checks. The
  fixture covers the valid route, annotated CLI output, wrong Stasis app, wrong
  DID variable, and noncontiguous steps (`tests/freepbx/test_bridge.php:71-90`);
  the final bridge run reports 23 checks passed.
- Disabled-app mapping recovery is supported. The API allows retaining the
  current disabled app only while disabling the number, while reassignment or
  re-enable still requires an enabled same-org app
  (`apps/control-api/app/phone_number_routes.py:130-158`). The UI exposes the
  unavailable current app with the disabled-only constraint and keeps enabled
  replacements available (`PhoneNumberForm.tsx:46-107`). Focused tests cover
  disable, reassignment, and rejection of re-enable against a disabled app
  (`tests/control-api/test_telephony_backend.py:225-320`).
- The operator guide now matches the supported subset: authentication is
  `none|outbound` and registration is `none|send`; native inbound/both and
  receive modes remain read-only (`docs/operations/sip-trunks-and-phone-numbers.md:72-94`).
- Explicit blank optional trunk fields are forwarded while omitted fields are
  preserved; unsupported native modes are protected from mutation; responses
  expose `password_set` rather than secrets; operator access and local mapping
  queries are organization-bound; nonempty `AI_GATEWAY_AGENT` precedence is
  preserved; deterministic route IDs support DB-commit retry; and failed
  Apply readback commits fail-closed `pbx_applied` state before returning 502.

## Unresolved limits

- This reviewer did not perform remote mutations. Root-run evidence covers
  live bridge/auth, browser DID/trunk edits, Apply, and native cleanup/invariant
  checks; it does not prove carrier/PSTN acceptance.
- The two residuals above remain rollout and recovery limits under the
  approved scope.

**Status:** DONE_WITH_CONCERNS
**Summary:** Final-source auth, header handoff, parser gate ordering, and root-run compatibility evidence are recorded. Exact route readback, disabled-app recovery, and trunk capability documentation are verified; the remaining accepted limits are native post-save recovery and the Apply active-channel count window.
**Concerns/Blockers:** No carrier/PSTN proof; no additional blocker found in the reviewed source or root-run evidence.

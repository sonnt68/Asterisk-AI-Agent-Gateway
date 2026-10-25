# Execution Plan: Default Outbound Scope

- Date: 2026-10-22
- Status: Complete
- Scope: new Partner App and default API-key requests only
- Implementation did not mutate existing apps/keys or rotate credentials. Safe live validation completed with zero active calls.

## Outcome

Give newly created Partner Apps and their default API keys `calls:originate` by default. Preserve explicit restricted scopes, validate every key as a subset of its app scopes, and leave existing apps, keys, active calls, and live credentials unchanged.

## Delivered behavior

- REST `AppRequest.scopes` defaults to `calls:read,media:stream,calls:originate`.
- Omitted REST `KeyRequest.scopes` uses the intersection of that shared default set and the owning app's current scopes. Explicit lists, including `[]`, remain exact and are still required to be subsets of app scopes.
- The Admin UI new-app form retains `calls:hangup` alongside read, media stream and originate; its issue-key action sends the selected app scopes.
- Existing apps and keys are unchanged and no key is auto-rotated or auto-issued.

## Design

1. **Backend default app scope** — in `apps/control-api/app/control_routes.py`, append `calls:originate` to the `AppRequest.scopes` default. Do not alter `validate_scopes` or the existing subset check.
2. **Backend default key scope** — make an omitted `KeyRequest.scopes` resolve to the intersection of the shared default set `{calls:read, media:stream, calls:originate}` and the owning app’s current scopes. A newly created app using backend defaults therefore issues a default key containing `calls:originate`; an app with extra transfer/dialplan scopes does not grant those implicitly. An explicitly supplied list, including `[]`, remains exact, normalized, allowlisted, and required to be a subset of app scopes.
3. **Admin default** — append `calls:originate` to `PartnerAppsPage.tsx` `DEFAULT_SCOPES`. Keep `useGatewayData.issueKey` sending the app’s scopes, and keep the existing dashboard path unchanged: its new-app defaults include originate, while explicitly configured app scopes remain intentional.
4. **Contract and owning docs** — update `packages/protocol/openapi.yaml` to document `calls:originate` in the Partner App default scope and the omitted-key intersection rule. Update `docs/operations/partner-onboarding.md` and `docs/project-changelog.md` with the new default and explicit-restriction behavior. Keep explicit scope examples and write-only key behavior intact; no SDK release.

## Exact implementation file list

Modify only:

- `apps/control-api/app/control_routes.py`
- `apps/admin-ui/src/pages/PartnerAppsPage.tsx`
- `tests/control-api/test_tenant_and_key_boundaries.py`
- `packages/protocol/openapi.yaml`
- `docs/operations/partner-onboarding.md`
- `docs/project-changelog.md`

Review-only confirmation: `apps/admin-ui/src/hooks/useGatewayData.tsx` already passes `app.scopes` to issue-key requests and needs no code change unless the implementation discovers a contract mismatch. No other implementation files are in scope.

## Current consumer configuration follow-up

The current setup, onboarding, SDK and handbook surfaces use
`GATEWAY_AGENT_SLUG` for environment exports and Copy configuration. Sample
readers accept `AGENT_SLUG` as a compatibility fallback where supported; SDK
arguments remain `agent_slug` and `agentSlug`. The current dial-out sample is
`sdks/python/examples/vindynamics-1-dial-out.py`, based on the direct
`sdks/python/examples/dial_out.py` flow.

## Behavior-level validation

- `AppRequest` with omitted scopes creates an app containing `calls:originate`; an explicit scope list is preserved after normalization.
- `KeyRequest` with omitted scopes uses only the default-set/app-scope intersection. A default app’s issued key contains `calls:originate` but no unrelated elevated scopes; an existing app explicitly restricted to `calls:read,media:stream` receives only those scopes when omitted, even if it has other app scopes. An explicit `[]` stays empty.
- An explicit key request containing `calls:originate` succeeds only when the app grants it; a request containing any ungranted or unsupported scope returns `422` and stores no key.
- Tenant isolation and existing Owner/Admin/Developer authorization remain unchanged. Key plaintext remains returned only through the existing explicit issue response and is not persisted in `secret_hash`.
- Admin browser check: create a new app and confirm the displayed default scope list includes `calls:originate`; issue its default key and confirm the request carries the app scope set. Confirm an explicitly restricted app/key remains restricted.
- Run the focused control-api tests, then `ruff`, the Admin UI build, and the repository validation command as required by the implementation workflow.

## Deployment risk and boundaries

- Granting `calls:originate` by default broadens outbound capability for newly created apps and keys. Existing destination-policy and command-scope enforcement remains the gate; test that no key can exceed its app scopes.
- Deployment did not mutate existing Partner Apps or API keys and did not rotate credentials. Existing live calls retained their current identity/scopes.
- Root is separately granting scopes to three existing live `vindynamics` apps/keys. That operation is outside this plan and is already separately verified; do not fold those mutations or any key rotation into this change.
- For an existing app whose scopes were not expanded, an omitted key-scope request uses the safe intersection, avoiding an unintended privilege expansion. To grant originate to that app, change its app scope through the separately authorized operation, then issue a new key explicitly or with omitted scopes; do not rotate existing keys as part of this plan.
- Safe live validation ran only with zero calls/connections before and after. It verified default and restricted scopes, unchanged existing credentials, no call impact, ARI/AudioSocket health, and cleanup. Authenticated browser click validation was limited by an expired Chrome session, and no full PSTN/carrier test is claimed.

## Verified validation and deployment evidence

- Full validation passed (`259` tests), focused scope-boundary checks passed
  (`8`), skill-package checks passed (`9`), and Ruff plus API/UI builds passed.
- API image `86650fa6d617b05d97e8ee31ac500a94ce07ff17321525a560cfc42d28a0d378`
  and UI image `0d631021932d1e676fecaa08984f73809a6ebcd6974fb3a3d13cad5f63aba03a`
  were deployed with backup
  `/opt/asterisk-ai-agent-gateway/backups/default-originate-env-20261022T105755Z`.
- Live REST fixtures verified default originate, explicit read/empty, null and
  ungranted `422`, and restricted-app exclusion of implicit transfer/originate.
  Two owned fixture apps were logically deleted and four owned keys revoked and
  purged. Three separately granted live Vindynamics keys produced public SDK
  `0.4` tokens effective for originate; old key material was preserved.
- The live `vindynamics-1-dial-out.py --check` reached `session.ready` and
  `heartbeat.ack` without dialing. The public asset confirmed the new env Copy
  label and dashboard originate default. No signed-in browser visual/Copy pass
  or full PSTN/carrier test is claimed.

## Progress and completion

- [x] Read README, AGENTS, workflow, control routes, Admin UI create/issue flow, boundary tests, and OpenAPI.
- [x] Implement the six-file change and focused tests.
- [x] Run repository checks, builds, package checks and live zero-call validation.
- [x] Reconcile current consumer env exports and sample fallback documentation.
- [x] Record bounded evidence and move this plan to `docs/plans/completed/`.

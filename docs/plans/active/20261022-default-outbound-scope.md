# Execution Plan: Default Outbound Scope

- Date: 2026-10-22
- Status: Active
- Scope: new Partner App and default API-key requests only
- No live mutation or existing-key rotation is part of this plan. Safe deployment validation is allowed only with zero active calls.

## Outcome

Give newly created Partner Apps and their default API keys `calls:originate` by default. Preserve explicit restricted scopes, validate every key as a subset of its app scopes, and leave existing apps, keys, active calls, and live credentials unchanged.

## Current behavior

- `AppRequest.scopes` defaults to `calls:read,media:stream`; the Admin UI create form uses its own `DEFAULT_SCOPES` and currently omits `calls:originate`.
- `KeyRequest.scopes` has a static default, while the Admin UI issue action already sends the selected app’s scopes.
- `ALLOWED_SCOPES` already contains `calls:originate`, and `create_key` already rejects a key scope outside the app scope set.
- The current create-app and issue-key actions are separate; this change does not auto-issue a key.

## Design

1. **Backend default app scope** — in `apps/control-api/app/control_routes.py`, append `calls:originate` to the `AppRequest.scopes` default. Do not alter `validate_scopes` or the existing subset check.
2. **Backend default key scope** — make an omitted `KeyRequest.scopes` resolve to the intersection of the shared default set `{calls:read, media:stream, calls:originate}` and the owning app’s current scopes. A newly created app using backend defaults therefore issues a default key containing `calls:originate`; an app with extra transfer/dialplan scopes does not grant those implicitly. An explicitly supplied list, including `[]`, remains exact, normalized, allowlisted, and required to be a subset of app scopes.
3. **Admin default** — append `calls:originate` to `PartnerAppsPage.tsx` `DEFAULT_SCOPES`. Keep `useGatewayData.issueKey` sending the app’s scopes, and keep the existing dashboard path unchanged: its new-app defaults include originate, while explicitly configured app scopes remain intentional.
4. **Contract and owning docs** — update `packages/protocol/openapi.yaml` to document `calls:originate` in the Partner App default scope and the omitted-key intersection rule. Update `docs/operations/partner-onboarding.md` and `docs/project-changelog.md` with the new default and explicit-restriction behavior. Keep explicit scope examples and write-only key behavior intact; no SDK release.

## Exact file list

Modify only:

- `apps/control-api/app/control_routes.py`
- `apps/admin-ui/src/pages/PartnerAppsPage.tsx`
- `tests/control-api/test_tenant_and_key_boundaries.py`
- `packages/protocol/openapi.yaml`
- `docs/operations/partner-onboarding.md`
- `docs/project-changelog.md`

Review-only confirmation: `apps/admin-ui/src/hooks/useGatewayData.tsx` already passes `app.scopes` to issue-key requests and needs no code change unless the implementation discovers a contract mismatch. No other product files are in scope.

## Behavior-level validation

- `AppRequest` with omitted scopes creates an app containing `calls:originate`; an explicit scope list is preserved after normalization.
- `KeyRequest` with omitted scopes uses only the default-set/app-scope intersection. A default app’s issued key contains `calls:originate` but no unrelated elevated scopes; an existing app explicitly restricted to `calls:read,media:stream` receives only those scopes when omitted, even if it has other app scopes. An explicit `[]` stays empty.
- An explicit key request containing `calls:originate` succeeds only when the app grants it; a request containing any ungranted or unsupported scope returns `422` and stores no key.
- Tenant isolation and existing Owner/Admin/Developer authorization remain unchanged. Key plaintext remains returned only through the existing explicit issue response and is not persisted in `secret_hash`.
- Admin browser check: create a new app and confirm the displayed default scope list includes `calls:originate`; issue its default key and confirm the request carries the app scope set. Confirm an explicitly restricted app/key remains restricted.
- Run the focused control-api tests, then `ruff`, the Admin UI build, and the repository validation command as required by the implementation workflow.

## Deployment risk and boundaries

- Granting `calls:originate` by default broadens outbound capability for newly created apps and keys. Existing destination-policy and command-scope enforcement remains the gate; test that no key can exceed its app scopes.
- Deploying this default does not mutate existing Partner Apps or API keys and does not rotate credentials. Existing live calls continue with their current identity/scopes.
- Root is separately granting scopes to three existing live `vindynamics` apps/keys. That operation is outside this plan and is already separately verified; do not fold those mutations or any key rotation into this change.
- For an existing app whose scopes were not expanded, an omitted key-scope request uses the safe intersection, avoiding an unintended privilege expansion. To grant originate to that app, change its app scope through the separately authorized operation, then issue a new key explicitly or with omitted scopes; do not rotate existing keys as part of this plan.
- After deployment, safe validation may run only when the live gateway reports zero active calls: verify new default app/key scopes, explicit restricted-key rejection, unchanged existing credentials, and no call impact. Stop if active calls are present; root owns this proof.

## Progress and completion

- [x] Read README, AGENTS, workflow, control routes, Admin UI create/issue flow, boundary tests, and OpenAPI.
- [ ] Implement the six-file change and focused tests.
- [ ] Run repository checks and record results.
- [ ] Keep this plan active until implementation and validation are complete; no live deployment claim is made here.

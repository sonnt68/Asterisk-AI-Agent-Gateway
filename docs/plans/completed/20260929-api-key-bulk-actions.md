# Execution Plan: Bulk API-key actions

Date: 2026-09-29

## Status

Active

## Outcome

Add row selection and select-all controls to API Keys, with confirmed bulk revoke and bulk permanent deletion of revoked keys; deploy the dashboard change to the existing pilot host after end-to-end proof.

## Context

- `docs/WORKFLOW.md`
- `docs/patterns/encoding-invariants.md`
- `docs/operations/partner-onboarding.md`: revoked keys must be revoked before permanent deletion; deletion remains audited.
- Existing `DELETE /api-keys/{key_id}` revokes and existing `DELETE /api-keys/{key_id}/purge` tenant-scopes and rejects active keys.
- Existing UI is `apps/admin-ui/src/pages/ApiKeysPage.tsx`; no UI test script exists, so use the dashboard smoke flow.

## Scope

In scope:

- Row checkboxes and a select-all checkbox over visible API-key rows.
- Bulk revoke selected active keys; bulk delete selected revoked keys only.
- Confirmation, per-key request completion, one refresh, and partial-failure reporting.
- Changelog update, production dashboard rebuild, and verification.

Out of scope:

- New backend endpoints or changes to revoke/purge contracts.
- Deleting active keys, unrelated staged files, or changes to API/database services.

## Approach

1. Add accessible checkbox state and status-filtered bulk actions in the page.
2. Add hook methods that call existing per-key endpoints, await all outcomes, refresh once, and report partial failures.
3. Update changelog; run admin build and exercise multi-key create/select/revoke/delete/audit in isolated Chromium/API/SQLite.
4. Back up the two server UI sources and current admin-ui image; transfer only those files, build/restart only `admin-ui`, then verify the live asset and API health.

## Risks And Recovery

- The actions are per-key requests, not an atomic transaction. Continue all selected eligible requests, refresh once, preserve failed IDs as selected, and report successes/failures.
- Delete eligibility remains revoked-only in both UI filtering and the existing server route.
- The dashboard is already public over plain HTTP. This change does not alter exposure; TLS remains required before real tenant traffic.
- On deploy failure, restore the saved UI files and pre-deployment admin-ui image. Do not restart the API or database.

## Progress

- [x] Inspect existing row actions, checkbox patterns, endpoint contracts, and lifecycle policy.
- [x] Implement bulk selection and actions; update changelog.
- [x] Build and prove the real local dashboard flow.
- [x] Deploy dashboard-only change; verify and move plan to `docs/plans/completed/`.

## Decisions

- 2026-09-29: Select-all covers all visible rows. Bulk revoke targets selected active rows; bulk delete targets selected revoked rows. The confirmation text names the eligible count, and ineligible selections are untouched.
- 2026-09-29: Reuse existing per-key endpoints rather than adding bulk API routes; continue all requests and retain failed IDs so partial outcomes are visible and retryable.

## Validation

- Admin build: `npm run admin:build` passed.
- Isolated browser/API smoke: partial and select-all states behaved correctly; bulk revoke affected active keys only; mixed-status delete removed revoked keys and preserved active keys; audit retained 4 revoke and 4 delete events.
- Remote deploy: `admin-ui` built and restarted only; `admin-ui`, API, Postgres, and Redis running; API health `ok`; dashboard HTTP 200; served bundle contains select-all, bulk-revoke, and bulk-delete controls.

## Result

Bulk API-key selection, status-scoped revoke/delete actions, changelog, and production dashboard deployment completed. Rollback UI sources and pre-deployment image retained; API and database were not changed.

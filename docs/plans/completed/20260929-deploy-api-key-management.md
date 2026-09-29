# Execution Plan: Deploy API-key management

Date: 2026-09-29

## Status

Completed

## Outcome

Deploy the API-key create and revoked-key deletion behavior to the user-authorized pilot host. Preserve a verified rollback path.

## Context

- `docs/operations/deployment.md`
- `docs/operations/backup-restore.md`
- The server is at `/opt/asterisk-ai-agent-gateway`; Compose services `api` and `admin-ui` are active.
- The server health endpoint is healthy and Alembic is at `0002_destination_policy` (head).
- The local feature has passing focused tests, Ruff, admin build, and isolated Chromium/API smoke proof.

## Scope

In scope:

- Deploy only `apps/admin-ui/src/pages/ApiKeysPage.tsx`, `apps/admin-ui/src/hooks/useGatewayData.tsx`, and `apps/control-api/app/key_management_routes.py`.
- Rebuild/restart `api` and `admin-ui`, then verify service health and the served dashboard.

Out of scope:

- Other staged changes in the local worktree.
- Database schema changes; this feature adds no migration.
- Changes to the existing public binding or TLS configuration.

## Approach

1. Stage the three target files on the server and verify their hashes.
2. Preserve the server's original source files and current API/UI images; install the target files.
3. Run the documented Compose build and restart for `api` and `admin-ui` only.
4. Verify Compose status, API health, Alembic head, and the deployed dashboard asset.
5. Retain rollback material until deployment is confirmed.

## Risks And Recovery

- API and dashboard may have a short restart interruption. The gateway, PostgreSQL, and Redis are not intentionally restarted.
- The server's dashboard is already exposed over plain HTTP; this deployment does not change that configuration. The deployment runbook says TLS is required before real tenant traffic.
- The admin-ui `npm ci` build reported two moderate npm audit findings; they were not investigated during this deployment.
- No database migration is expected: the server is already at the local migration head. If startup fails, restore the saved source files and previous API/UI images; do not downgrade the database.

## Progress

- [x] Confirm target, running services, current health, migration head, and existing source versions.
- [x] Stage, back up, and install the three feature files.
- [x] Build/restart the API and dashboard; verify deployment.
- [x] Record result and move this plan to `docs/plans/completed/`.

## Decisions

- 2026-09-29: Deploy only the three runtime files for this feature; the local worktree contains 30 other staged files and is two commits behind `origin/main`, so do not deploy unrelated changes or sync the entire tree.
- 2026-09-29: Do not back up or migrate PostgreSQL; the feature adds no schema and the server is already at migration head. Preserve source/image rollback points instead.

## Validation

- Focused proof before deployment: 5 pytest/contract tests passed; Ruff passed; `npm run admin:build` passed; isolated browser/API smoke passed through key creation, revocation, deletion, and audit retention.
- Deployment proof:
  - All four Compose services (`api`, `admin-ui`, `postgres`, `redis`) are running.
  - API health returns `status: ok`; Alembic remains at `0002_destination_policy` (head).
  - Runtime OpenAPI exposes `DELETE /api/v1/api-keys/{key_id}/purge` with 204; its generated schema does not list explicit 404/409 responses. The repository protocol spec documents those responses, and local tests prove them.
  - The deployed dashboard returns HTTP 200; Chromium verified the login page and the served JavaScript bundle contains the create/delete controls and purge path.

## Result

Deployed only the three API-key feature source files. Rebuilt and restarted `api` and `admin-ui`; PostgreSQL and Redis stayed running. Preserved original source files and prior images for rollback, and removed temporary transfer files. No new schema migration was needed.

The dashboard remains publicly reachable over plain HTTP, as before; the deployment runbook requires TLS before real tenant traffic. The container build also surfaced two moderate npm audit findings that were not assessed.

# Phase 04: Multi-tenant auth, API keys and dashboard

## Context links

- [Overview](plan.md)
- [AVA findings](research/ava-asterisk-integration-findings.md)
- Source references: `admin_ui/frontend/src/components/layout/`, `LoginPage.tsx`, `AuthContext.tsx`, `SECURITY.md`

## Overview

- Priority: P0
- Status: Complete
- Goal: provide a secure control plane for operators and third-party developers.

## Key insights

- AVA's visual shell is reusable, but its `users.json` and Docker-socket trust model are not.
- API key lifecycle needs tenant ownership, scopes, one-time reveal, rotation, revocation and audit.
- Dashboard auth and machine API-key auth are separate mechanisms.

## Requirements

- PostgreSQL models: organizations, users, memberships, the single MVP Asterisk configuration, partner apps, routes, API keys, calls, outbound jobs and audit logs.
- Roles: owner, admin, developer, viewer with server-side authorization on every resource.
- Passwords hashed with Argon2id; browser auth uses Secure, HttpOnly, SameSite cookies and CSRF protection.
- API key format with environment and prefix, for example `agw_live_<prefix>_<secret>`.
- Store only prefix, HMAC/SHA-256 hash, scopes, timestamps, creator, expiry and revocation state.
- Dashboard pages: overview, Asterisk connection, partner apps, routing, API keys, live connections, calls, audit log and organization members.
- Dashboard includes call-control scope/allowlist policy and outbound call lifecycle management.
- No raw secret, ARI password or API key returned after initial reveal.

## Architecture

```text
Browser session auth -> RBAC service -> tenant-scoped control API -> PostgreSQL
Machine API key -----> key verifier -> scoped machine API
                                      -> audit event stream
```

Minimum control API:

- `POST /v1/auth/login`, `POST /v1/auth/logout`, `GET /v1/auth/session`
- `GET/POST /v1/organizations/{org_id}/partner-apps`
- `GET/POST /v1/partner-apps/{app_id}/routes`
- `GET/POST /v1/partner-apps/{app_id}/api-keys`
- `POST /v1/api-keys/{key_id}/rotate`, `DELETE /v1/api-keys/{key_id}`
- `GET /v1/connections`, `GET /v1/calls`, `GET /v1/audit-events`
- `POST /v1/outbound-calls`, `GET /v1/outbound-calls/{call_id}`, `DELETE /v1/outbound-calls/{call_id}`

## Related code files

Create in new repository:

- `apps/control-api/auth/`, `organizations/`, `api-keys/`, `routes/`, `audit/`
- `apps/control-api/db/models/`, `db/migrations/`
- `apps/admin-ui/src/auth/`
- `apps/admin-ui/src/components/layout/`
- `apps/admin-ui/src/pages/dashboard/`, `api-keys/`, `partner-apps/`, `routes/`, `calls/`
- `tests/security/tenant-isolation/`, `tests/api/api-keys/`

## Implementation steps

1. Copy and rebrand approved AVA shell/theme/components with MIT notice.
2. Implement user bootstrap/login/logout/refresh/recovery and organization membership.
3. Enforce tenant scoping in repositories/services, not only route handlers.
4. Implement create/list/revoke/rotate API-key lifecycle with one-time reveal dialog.
5. Add scopes, expiry, last-used metadata and rate-limit configuration.
6. Add partner app, agent slug, concurrency and route management.
7. Add call-control scopes, destination allowlists and outbound call pages.
8. Add the single Asterisk connection status and call/session observability without Docker socket access.
9. Add append-only audit events for auth, key, route, call-control and configuration changes.

## Todo list

- [x] Database migrations
- [x] User/session auth and RBAC
- [x] Tenant-isolated repositories
- [x] API key lifecycle
- [x] Gateway dashboard pages
- [x] Audit log
- [x] Accessibility and responsive build verification

## Success criteria

- Two organizations cannot read, route, revoke or observe each other's resources.
- API key plaintext is visible once and cannot be recovered from DB or logs.
- Revocation and expiry appear in UI and are enforced by token exchange.
- Dashboard works without host filesystem or Docker socket privileges.

## Risk assessment

- UI copy carries obsolete dependencies: upgrade and run frontend audit before release.
- Authorization drift: central policy service plus negative cross-tenant tests.
- Account recovery abuse: rate-limit, audit and require verified operator flow.
- Key prefix collision: sufficiently long random prefix and unique DB constraint.

## Security considerations

- Separate browser/session keys, realtime signing keys and API-key hashing pepper.
- Encrypt sensitive Asterisk configuration with managed secret storage.
- Redact PII and secrets in logs; define call metadata retention controls.
- Require MFA/SSO for operators before public production launch if centrally hosted.

## Next steps

Publish SDKs, connection documentation and the AI Coding skill in Phase 05.

## Unresolved questions

- Required identity providers: local account only, Google/Microsoft OIDC, or enterprise SSO.
- Whether third-party users can access the dashboard or only receive machine credentials.

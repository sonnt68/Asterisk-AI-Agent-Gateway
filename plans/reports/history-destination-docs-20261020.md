# CMS call-history destination details docs — 2026-10-20

## Outcome

Updated the smallest internal documentation surfaces for nullable
`called_number` and `routing_context` metadata. The docs describe browser-only
CMS detail exposure, existing tenant authorization, validated outbound and
trusted inbound capture, unchanged partner/realtime/SDK contracts, null legacy
rows, and exact-only future backfill correlation.

## Files changed

- `docs/security-model.md`
- `docs/operations/deployment.md`
- `docs/project-changelog.md`

## Validation

- Focused implementation evidence: `38 passed, 4 warnings` across call-history
  API/store and outbound lifecycle tests. Warnings are the existing aiohttp
  `BasicAuth` deprecation warnings.
- Internal-doc assertions and `git diff --check` passed.
- No deployment, migration rollout, or legacy backfill completion is claimed.

## Docs impact

Minor: internal security and deployment guidance plus the dated changelog entry.
No customer/SDK documentation was changed.

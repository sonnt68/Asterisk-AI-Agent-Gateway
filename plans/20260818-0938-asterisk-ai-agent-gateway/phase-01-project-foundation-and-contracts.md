# Phase 01: Project foundation and contracts

## Context links

- [Overview](plan.md)
- [AVA findings](research/ava-asterisk-integration-findings.md)
- Source references: `README.md`, `LICENSE`, `src/ari_client.py`, `admin_ui/frontend/package.json`

## Overview

- Priority: P0
- Status: Pending approval
- Goal: create the independent repository and freeze its public/internal boundaries before implementation.

## Key insights

- Reuse AVA patterns selectively; do not fork the entire AI provider engine.
- Public REST and realtime contracts must be versioned before SDK/dashboard implementation.
- Keep control plane, telephony plane and partner realtime plane separate in code and deployment.

## Requirements

- Create `/Users/mac/workspace/sonnt/Asterisk-AI-Agent-Gateway` as a new sibling git repository; never implement gateway code inside the AVA checkout.
- Preserve MIT attribution for copied AVA code/assets and record exact source commit.
- Stack: Python 3.12/FastAPI/asyncio, React 18 + TypeScript + Vite + Tailwind, PostgreSQL, Redis.
- Container-first local development with separate `gateway`, `api`, `worker`, `admin-ui`, `postgres`, `redis` services only where separation is real.
- Establish Python and TypeScript formatting, linting, type checking and test commands.
- Model one configured Asterisk instance for MVP; postpone multi-PBX abstractions until a verified requirement exists.

## Architecture

```text
apps/gateway       ARI, transports, call state, realtime broker
apps/control-api   users, orgs, apps, keys, routes, audit APIs
apps/admin-ui      AVA-derived shell and gateway management pages
packages/protocol  OpenAPI, AsyncAPI, generated shared types
sdks/              Python and Node client SDKs
docs/              operator and partner documentation
.agents/skills/    repository-owned AI Coding skill
```

One deployable may initially run `gateway` and `control-api` in one process, but module boundaries and schemas remain explicit.

## Related code files

Create in new repository:

- `pyproject.toml`, `package.json`, `docker-compose.yml`, `.env.example`
- `apps/gateway/`, `apps/control-api/`, `apps/admin-ui/`
- `packages/protocol/openapi.yaml`, `packages/protocol/asyncapi.yaml`
- `tests/contract/`, `tests/integration/`
- `docs/architecture.md`, `docs/security-model.md`

## Implementation steps

1. Initialize repo, license/NOTICE and contributor instructions.
2. Copy only approved AVA UI shell, theme, auth screens and generic UI primitives.
3. Create backend modules with dependency direction enforced by imports/tests.
4. Define canonical IDs, timestamps, error envelope, pagination and API versioning.
5. Draft OpenAPI for control endpoints and AsyncAPI for realtime events.
6. Add schema generation and breaking-change checks to CI.
7. Record decisions for AudioSocket-first transport and outbound partner WSS.

## Todo list

- [ ] New repository initialized
- [ ] AVA attribution recorded
- [ ] Module boundaries compile
- [ ] OpenAPI and AsyncAPI validate
- [ ] CI runs focused tests, lint, typecheck and build

## Success criteria

- Fresh clone starts dependencies and placeholder services with one documented command.
- Protocol schemas generate Python/TypeScript models without manual edits.
- No copied provider/model/Docker-control surface exists in the new repo.

## Risk assessment

- Risk: accidental monolithic AVA fork. Mitigation: explicit allowlist of copied UI/code files.
- Risk: premature service sprawl. Mitigation: logical modules first, split processes only for scaling/security boundaries.
- Rollback: delete the unshipped new repo; source AVA remains untouched.

## Security considerations

- `.env`, keys, credentials and generated runtime data are gitignored and secret-scanned.
- No Docker socket mount in public-facing services.
- Threat model and trust boundaries are required before API implementation.

## Next steps

Proceed to Phase 02 after public schemas and module boundaries are approved.

## Unresolved questions

- Final public product branding; repository/path is fixed as `Asterisk-AI-Agent-Gateway`.
- Whether PostgreSQL migrations use Alembic or another existing organizational standard.

# Asterisk AI Agent Gateway

A SaaS gateway that connects one Asterisk instance to third-party AI agents. The gateway owns ARI, Stasis, bridges and telephony media; partners connect with a scoped API key through a simple outbound WebSocket SDK.

## Status

Phase 01 foundation. The public REST and realtime contracts are versioned before telephony and dashboard implementation.

## Architecture

```text
Asterisk -- ARI + AudioSocket --> Gateway -- WSS --> Partner AI SDK
                                  |
                           PostgreSQL / Redis
                                  |
                             Admin dashboard
```

## Scope

- One configured Asterisk instance for the MVP.
- Multi-tenant SaaS control plane with organizations, API keys and audit logs.
- Full partner call control, gated by scopes and destination policies.
- No built-in AI providers, Docker socket management or direct partner access to Asterisk credentials.

## Reference and attribution

The project uses the Asterisk AI Voice Agent repository as a reference for ARI, AudioSocket, transport reliability and selected dashboard UX patterns. It is an independent repository and does not include AVA's provider engine or host-control surfaces. See [NOTICE](NOTICE).

## Plan

The approved implementation plan is in [plans/20260818-0938-asterisk-ai-agent-gateway](plans/20260818-0938-asterisk-ai-agent-gateway/plan.md).

## Local development

Requires Python 3.12+ and Node.js 22+.

```bash
python3.14 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
npm --prefix apps/admin-ui install
.venv/bin/ruff check apps tests
.venv/bin/pytest
npm run admin:build
```

To run the local container stack, copy `.env.example` to `.env`, replace the
placeholder PostgreSQL and Asterisk values, then run:

```bash
docker compose up --build
```

The Asterisk adapter is intentionally not connected in this foundation phase;
the API health endpoint is available at `http://localhost:8080/api/v1/system/health`
and the dashboard shell at `http://localhost:5173`.

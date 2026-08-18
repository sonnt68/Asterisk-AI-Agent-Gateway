# Code standards

- Keep partner contracts independent of ARI IDs and transport details.
- Validate tenant, scope and destination allowlist before ARI calls.
- Store API-key hashes only; never log secrets or raw audio.
- Use Alembic for schema changes and test fresh-database upgrades.
- Keep cleanup idempotent and verify active calls/media return to zero.
- Run Ruff, pytest, UI/SDK builds, protocol and skill validation for public changes.

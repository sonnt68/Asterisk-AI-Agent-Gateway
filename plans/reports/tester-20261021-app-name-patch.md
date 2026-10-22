# Tester report: editable Partner App name

Date: 2026-10-21
Scope: dashboard PATCH contract for Partner App display names.

## Changes

- Extended `tests/control-api/test_partner_app_deletion.py` with real TestClient/SQLite coverage for trimmed valid rename.
- The positive case verifies slug, API-key metadata, DID-to-app mapping, call-history agent identity, and allowed-destination routing policy remain unchanged.
- Negative cases verify blank and 121-character names return 422 without mutation, and a foreign-organization app returns 404 without mutation or update audit.

## Validation

- Focused PATCH/deletion tests: **12 passed**.
- Admin UI build: passed (`tsc -b`, Vite).
- `bash scripts/validate.sh`: **254 passed**, 11 warnings; protocol/config checks and both repository builds passed.
- Public Node SDK tests: **24 passed**.
- No live calls, deployment, PBX mutation, or external tests performed.

Warnings are existing dependency/runtime deprecations: `aiohttp.BasicAuth` and Python 3.14 SQLite datetime adapter.

## Unresolved questions

- None for the owned test scope.

# Tester report: Partner App deletion and API-key copy

Date: 2026-10-21
Scope: control API deletion tombstones, encrypted persistent key copy, and migration preservation.

## Changes

- Added `tests/control-api/test_partner_app_deletion.py` with real SQLite/SQLAlchemy state and TestClient coverage for explicit revoke-then-delete, active enabled/disabled key rejection, expired-but-unrevoked key rejection, no-mutation/no-audit failure state, retained phone/call/signal history, hidden deleted apps, disabled-app listing, tenant/role/origin boundaries, repeated deletion, slug reservation, and deleted-app route/auth rejection.
- Added `tests/control-api/test_api_key_copy.py` with real Fernet coverage for encrypted create/reveal, list redaction and `copy_available`, rotation binding, legacy hash-only behavior, wrong/missing key handling, tampering and cross-row ciphertext swaps, expiry/disable/revoke states, role/tenant/origin checks, and audit redaction.
- Updated `tests/control-api/test_phone_numbers_migration.py` to assert nullable migration columns and preserve pre-migration rows using raw old-schema inserts, including no outbound backfill.

## Validation

- Focused Ruff: passed.
- Focused tests: **19 passed**, 5 SQLite datetime adapter deprecation warnings.
- `bash scripts/validate.sh`: **250 passed**, 11 warnings; protocol/config checks passed; admin UI build passed; `packages/node-sdk` build passed.
- Canonical public Node SDK tests: **24 passed**, 0 failed.
- No live calls, deployment, PBX mutation, or external tests performed.

Warnings are existing dependency/runtime deprecations: `aiohttp.BasicAuth` and Python 3.14 SQLite datetime adapter.

## Unresolved questions

- None for the owned test scope.

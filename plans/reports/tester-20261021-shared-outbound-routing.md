# Shared outbound routing validation

Date: 2026-10-21

## Results

- Focused routing/migration/runtime/SDK Python suite: `61 passed, 6 warnings`.
- `npm --prefix sdks/node test`: passed, `24` Node tests.
- `bash scripts/validate.sh`: passed, `234 passed, 6 warnings`; Admin UI production build and canonical Node SDK TypeScript build passed.
- Added real loopback wire checks for Python and Node SDKs: omitted `caller_number` preserves the exact legacy payload, explicit caller number uses the wire field, and malformed values fail before sending.
- Added API and SQLite coverage for outbound association create/patch preserve/clear, same-org Owner/Admin access, disabled-app retention/new-assignment rejection, cross-org rejection, composite foreign keys, and migration no-backfill preservation.
- Added runtime coverage for zero/one/multiple eligible numbers, exact selection, stale disabled grants, disabled apps with zero grants, cross-org rows, inbound owner precedence, caller-ID ARI parameters, FreePBX override variables, and no reservation/ARI side effects on selection failure.

## Warnings

The six focused and full-suite warnings are existing `aiohttp.BasicAuth` deprecation warnings from `apps/control-api/app/outbound_calls.py:75`.

## Limits

- Tester did not deploy, write native PBX state, or place carrier/PSTN calls.
- Root reported the native FreePBX internal caller-ID proof separately; it is not claimed as tester-executed evidence here.
- `apps/admin-ui/tsconfig.tsbuildinfo` was refreshed by the required production build and is shared generated state.

## Unresolved questions

- None for the assigned local test scope.

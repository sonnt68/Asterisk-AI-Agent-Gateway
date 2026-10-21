# Telephony validation report

Date: 2026-10-21

## Results

- `bash scripts/validate.sh`: passed — Ruff, 214 pytest cases, protocol/config parsing, shell validation, Admin UI production build, and Node SDK TypeScript build.
- Focused telephony/PBX suite: 6 passed — `test_telephony_backend.py`, `test_managed_inbound_routing.py`, `test_phone_numbers_migration.py`, and `tests/freepbx`.
- PHP syntax: passed for every file under `integrations/freepbx/` and `tests/freepbx/`.
- FreePBX bridge regression: `freepbx bridge checks: 22 passed`.
- Node SDK: `npm --prefix packages/node-sdk run build` passed. No Node test script or test files are present in this checkout.
- Live probe script: `python3 -m py_compile tests/e2e/asterisk/live-telephony-probe.py`, Ruff, import smoke check, and sanitized preflight failure check passed. Live execution remains root-owned after deployment.

## Notes

The Admin UI build updated the tracked `apps/admin-ui/tsconfig.tsbuildinfo` artifact to include the new telephony sources; it was not edited manually. The working tree already contained the other feature changes from the collaborating agents.

## Unresolved questions and limits

- The live FreePBX bootstrap/deployment remains a deployment concern; no native FreePBX host was available in this local run.
- No carrier, PSTN, or live Asterisk call was attempted from this tester subtask.

## Controller follow-up

After the local tester run, final Apache header/BMO bootstrap compatibility and
native source-annotation parser changes passed PHP lint and 23 bridge checks.
Root deployed and executed the internal A-to-B routing/media/disable probe and
browser saves/Apply, then verified fixture cleanup and native settings
preservation. These are root-run observations; see the completed rollout plan.

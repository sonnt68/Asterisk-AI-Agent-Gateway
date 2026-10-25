# Tester report: default originate scope and Vindynamics export

Date: 2026-10-22
Scope: new-app/key default scopes, copied-config env name, exported Vindynamics-1 sample, and partner skill examples.

## Validation

- Focused boundary tests: **8 passed** (`tests/control-api/test_tenant_and_key_boundaries.py`). Covered new-app `calls:originate`, omitted-key intersection with app scopes, no excess powers, explicit `[]`, explicit originate, rejected unsupported/ungranted scopes, and explicit `null` validation.
- `bash scripts/validate.sh`: **259 passed**, 11 existing deprecation warnings; OpenAPI/config checks, admin UI build, and package SDK build passed.
- Partner skill package test: **9 passed** (`tests/test_partner_skill_package.py`).
- Exported `sdks/python/examples/vindynamics-1-dial-out.py`: 189 lines, Ruff clean, Python compile passed, copied-config `--help` passed using `/tmp/gateway-copied-config-check-20261021/bin/python` with official SDK **0.4.0**.
- Python compile passed for changed examples; `node --check` passed for the root and both partner-skill `echo-agent.mjs` copies.
- Invalid-argument sample failure did not echo a sentinel API key. SDK error definitions also retain status-only HTTP diagnostics.
- Dashboard Copy config uses `GATEWAY_AGENT_SLUG`; all six partner-skill example copies prefer that variable and retain `AGENT_SLUG` fallback.

No live server operation, dialing, deployment, or credential mutation was performed by this tester. Root owns live proof.

The dirty tree already contained the generated `apps/admin-ui/tsconfig.tsbuildinfo`; it was preserved and not restored.

## Unresolved questions

- None for the requested local validation scope.

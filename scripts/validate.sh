#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"

.venv/bin/ruff check apps tests
.venv/bin/pytest -q
.venv/bin/python -c \
  'import yaml; [yaml.safe_load(open(path)) for path in ("packages/protocol/openapi.yaml", "packages/protocol/asyncapi.yaml", "observability/alerts/gateway-rules.yaml")]'
.venv/bin/python -m json.tool observability/dashboards/gateway-overview.json >/dev/null
bash -n tests/chaos/run-dependency-recovery.sh
npm --prefix apps/admin-ui run build
npm --prefix packages/node-sdk run build

echo "Repository validation passed"

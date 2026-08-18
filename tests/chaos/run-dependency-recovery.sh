#!/usr/bin/env bash
set -euo pipefail

project_dir="${1:-/opt/asterisk-ai-agent-gateway}"
cd "$project_dir"

health_url="http://127.0.0.1:${GATEWAY_API_PORT:-18080}/api/v1/system/health"
metrics_url="http://127.0.0.1:${GATEWAY_API_PORT:-18080}/api/v1/system/metrics"

docker compose restart api >/dev/null
for attempt in {1..20}; do
  curl -fsS "$health_url" >/dev/null && break
  sleep 1
done
curl -fsS "$health_url" >/dev/null
curl -fsS "$metrics_url" | grep -q '^gateway_ari_connected 1.0$'

docker compose pause redis >/dev/null
trap 'docker compose unpause redis >/dev/null 2>&1 || true' EXIT
curl -fsS "$health_url" >/dev/null
if docker compose exec -T api python -c \
  'import os, redis; redis.Redis.from_url(os.environ["REDIS_URL"], socket_timeout=1).ping()' \
  >/dev/null 2>&1; then
  echo "Redis interruption was not observed" >&2
  exit 1
fi
docker compose unpause redis >/dev/null
trap - EXIT
docker compose exec -T api python -c \
  'import os, redis; assert redis.Redis.from_url(os.environ["REDIS_URL"], socket_timeout=1).ping()'

docker compose pause postgres >/dev/null
trap 'docker compose unpause postgres >/dev/null 2>&1 || true' EXIT
curl -fsS "$health_url" >/dev/null
docker compose unpause postgres >/dev/null
trap - EXIT
docker compose exec -T postgres pg_isready -U "${POSTGRES_USER:-asterisk_ai_gateway}" \
  -d "${POSTGRES_DB:-asterisk_ai_gateway}" >/dev/null

echo '{"status":"passed","ari_reconnect":true,"redis_recovery":true,"postgres_recovery":true}'

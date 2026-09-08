#!/usr/bin/env bash
# End-to-end UI tests against the local stack.
set -euo pipefail
cd "$(dirname "$0")/.."

STARTED_COMPOSE=0
STARTED_ROUTER=0
cleanup() {
  [[ "$STARTED_ROUTER" == 1 ]] && pkill -f "uvicorn app.main:app" 2>/dev/null || true
  [[ "$STARTED_COMPOSE" == 1 ]] && docker compose down >/dev/null 2>&1 || true
}
trap cleanup EXIT

[[ -d frontend/dist ]] || (cd frontend && npm ci && npm run build)

if ! curl -sf localhost:9001/healthz >/dev/null 2>&1; then
  docker compose up -d
  STARTED_COMPOSE=1
  for _ in $(seq 1 30); do
    curl -sf localhost:9001/healthz >/dev/null 2>&1 && break
    sleep 1
  done
fi

if ! curl -sf localhost:8000/v1/conversations >/dev/null 2>&1; then
  APP_DB_PATH=$(mktemp -d)/e2e.db uv run uvicorn app.main:app --port 8000 >/tmp/router-e2e.log 2>&1 &
  STARTED_ROUTER=1
  for _ in $(seq 1 20); do
    curl -sf localhost:8000/v1/conversations >/dev/null 2>&1 && break
    sleep 1
  done
fi

cd frontend
npx playwright install --with-deps chromium 2>/dev/null || npx playwright install chromium
npx playwright test

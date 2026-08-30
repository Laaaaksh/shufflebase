#!/usr/bin/env bash
# Boots a real Postgres, seeds the demo schema, starts `shufflebase serve`,
# records a genuine Playwright walkthrough, converts it to mp4/gif, and tears
# everything down. This is what `make demo` runs.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CONTAINER=shufflebase-demo-pg
PG_PORT=5540
APP_PORT=8642
SOURCE_URL="postgresql+psycopg://postgres:demo@127.0.0.1:${PG_PORT}/proddb"
TARGET_URL="postgresql+psycopg://postgres:demo@127.0.0.1:${PG_PORT}/staging"

cleanup() {
  [[ -n "${SERVE_PID:-}" ]] && kill "$SERVE_PID" 2>/dev/null || true
  docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "==> starting Postgres ($CONTAINER on port $PG_PORT)"
docker run --rm -d --name "$CONTAINER" -p "${PG_PORT}:5432" \
  -e POSTGRES_PASSWORD=demo -e POSTGRES_DB=proddb postgres:16-alpine >/dev/null
until docker exec "$CONTAINER" pg_isready -U postgres >/dev/null 2>&1; do sleep 0.5; done

echo "==> seeding source database"
docker cp "$ROOT/examples/demo/seed.sql" "$CONTAINER":/tmp/seed.sql
docker exec "$CONTAINER" psql -U postgres -d proddb -f /tmp/seed.sql >/dev/null

echo "==> creating a fresh target database"
docker exec "$CONTAINER" psql -U postgres -d postgres -c "DROP DATABASE IF EXISTS staging;" >/dev/null
docker exec "$CONTAINER" psql -U postgres -d postgres -c "CREATE DATABASE staging;" >/dev/null

cd "$ROOT"
if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
# shellcheck source=/dev/null
source .venv/bin/activate
pip show shufflebase >/dev/null 2>&1 || pip install -q -e ".[postgres,web]"

echo "==> starting shufflebase serve on port $APP_PORT"
shufflebase serve --port "$APP_PORT" &
SERVE_PID=$!
for _ in $(seq 1 30); do
  curl -sf "http://127.0.0.1:${APP_PORT}" >/dev/null 2>&1 && break
  sleep 0.5
done

echo "==> recording"
cd "$ROOT/scripts/record-demo"
[[ -d node_modules ]] || npm install
npx playwright install chromium --with-deps >/dev/null 2>&1 || npx playwright install chromium

SHUFFLEBASE_DEMO_CONTAINER="$CONTAINER" \
SHUFFLEBASE_DEMO_APP_URL="http://127.0.0.1:${APP_PORT}" \
SHUFFLEBASE_DEMO_SOURCE_URL="$SOURCE_URL" \
SHUFFLEBASE_DEMO_TARGET_URL="$TARGET_URL" \
node record.js

echo "==> converting to mp4/gif"
"$ROOT/scripts/record-demo/convert.sh"

echo "==> done: docs/assets/demo.mp4 and docs/assets/demo.gif"

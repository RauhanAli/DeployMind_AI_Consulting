#!/usr/bin/env bash
# Start API (8000), Celery worker + beat, and the Next.js web app (3000) in the background.
# Requires: docker compose up -d postgres redis; apps/api/.venv installed; pnpm install; web built (pnpm build:web)
# unless WEB_MODE=dev. Logs: var/log/*.log. Each service runs in its own session so dev-stop.sh can stop
# the whole process group (npx/uvicorn/celery spawn child processes).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$ROOT/var/run" "$ROOT/var/log"
"$ROOT/scripts/dev-stop.sh" >/dev/null || true

cd "$ROOT/apps/api"
setsid nohup .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 > "$ROOT/var/log/api.log" 2>&1 &
echo $! > "$ROOT/var/run/api.pid"
setsid nohup .venv/bin/celery -A app.workers.celery_app worker -B -l info --concurrency 2 > "$ROOT/var/log/worker.log" 2>&1 &
echo $! > "$ROOT/var/run/worker.pid"

cd "$ROOT/apps/web"
if [ "${WEB_MODE:-start}" = "dev" ]; then
  setsid nohup npx next dev -p 3000 > "$ROOT/var/log/web.log" 2>&1 &
else
  setsid nohup npx next start -p 3000 > "$ROOT/var/log/web.log" 2>&1 &
fi
echo $! > "$ROOT/var/run/web.pid"

for i in $(seq 1 30); do
  if curl -fs http://localhost:8000/health >/dev/null && curl -fs -o /dev/null http://localhost:3000/; then
    echo "DeployMind is running: web http://localhost:3000 · API http://localhost:8000/docs"
    exit 0
  fi
  sleep 1
done
echo "Services did not become healthy in 30s; see var/log/*.log" >&2
exit 1

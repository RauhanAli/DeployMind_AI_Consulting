#!/usr/bin/env bash
# Stop processes started by dev-start.sh (PID files in var/run).
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
for name in web worker api; do
  f="$ROOT/var/run/$name.pid"
  if [ -f "$f" ]; then
    pid=$(cat "$f")
    if kill -0 "$pid" 2>/dev/null; then
      # negative pid = the whole process group created by setsid in dev-start.sh
      kill -- "-$pid" 2>/dev/null || kill "$pid" 2>/dev/null
      echo "stopped $name ($pid)"
    fi
    rm -f "$f"
  fi
done

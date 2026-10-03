#!/usr/bin/env bash
# One-command local dev launcher for stock-desk (backend + scheduler + frontend).
# Run from anywhere inside the repo: `bash apps/stock-desk/dev-up.sh`.
# Backend and scheduler MUST be started from the backend directory so the default
# SQLite path (./data/stock-desk.db) resolves to the same database file for both.
# Order: pull -> backend -> wait for /health -> scheduler -> frontend -> status lines.
set -euo pipefail

TARGET_BRANCH="product/stock-desk"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BACKEND_DIR="$REPO_ROOT/apps/stock-desk/backend"
FRONTEND_DIR="$REPO_ROOT/apps/stock-desk/frontend"

BACKEND_PID=""
SCHEDULER_PID=""
FRONTEND_PID=""

# Stop all child processes together on Ctrl+C / script exit.
cleanup() {
  trap - EXIT INT TERM
  local pid
  for pid in "$FRONTEND_PID" "$SCHEDULER_PID" "$BACKEND_PID"; do
    if [ -n "$pid" ]; then
      # Reap grandchildren first (uvicorn reload worker, next dev's node):
      # background jobs ignore SIGINT, so Ctrl+C alone would leave them behind.
      pkill -P "$pid" 2>/dev/null || true
      kill "$pid" 2>/dev/null || true
    fi
  done
  wait 2>/dev/null || true
}
trap cleanup EXIT
trap 'exit 130' INT TERM

# Returns 0 when the URL answers with a non-error status.
probe() {
  if command -v curl >/dev/null 2>&1; then
    curl -s -f --max-time 3 -o /dev/null "$1"
  else
    python3 -c "import sys,urllib.request; urllib.request.urlopen(sys.argv[1], timeout=3)" "$1" >/dev/null 2>&1
  fi
}

# wait_for URL LABEL MAX_TRIES PID: poll every 2s; give up early if the process died.
wait_for() {
  local url="$1" label="$2" max_tries="$3" pid="$4" tries=0
  echo "    Waiting for $label (up to $((max_tries * 2)) seconds)..."
  until probe "$url"; do
    if ! kill -0 "$pid" 2>/dev/null; then
      echo "[ERROR] $label process exited before it became ready. See the messages above."
      return 1
    fi
    tries=$((tries + 1))
    if [ "$tries" -ge "$max_tries" ]; then
      echo "[TIMEOUT] $label did not answer at $url in time. See the messages above."
      return 1
    fi
    sleep 2
  done
}

# ---- 1. pull latest code (never fatal: dirty tree / wrong branch / offline just skip) ----
echo "==> [1/4] Updating code (git pull)"
CUR_BRANCH="$(git -C "$REPO_ROOT" rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)"
if [ "$CUR_BRANCH" != "$TARGET_BRANCH" ]; then
  echo "[SKIP] Current branch is $CUR_BRANCH, not $TARGET_BRANCH. Not pulling; running the code as it is."
elif [ -n "$(git -C "$REPO_ROOT" status --porcelain --untracked-files=no)" ]; then
  echo "[SKIP] You have uncommitted changes to tracked files. Not pulling; running the local code as it is."
  echo "       Commit or stash them, then run this script again if you want the latest code."
elif ! git -C "$REPO_ROOT" pull --ff-only origin "$TARGET_BRANCH"; then
  echo "[SKIP] git pull failed (offline, or the branch cannot fast-forward). Running the local code as it is."
fi

# ---- 2. backend ----
echo "==> [2/4] Starting backend on :8000"
(cd "$BACKEND_DIR" && exec uv run uvicorn app.main:app --reload --port 8000) &
BACKEND_PID=$!
wait_for "http://localhost:8000/health" "backend" 30 "$BACKEND_PID"

# ---- 3. scheduler (only after the backend is healthy) ----
echo "==> [3/4] Starting scheduler (python -m app.scheduler)"
(cd "$BACKEND_DIR" && exec uv run python -m app.scheduler) &
SCHEDULER_PID=$!

# ---- 4. frontend ----
echo "==> [4/4] Starting frontend on :3000 (Ctrl+C stops all three)"
(cd "$FRONTEND_DIR" && exec npm run dev) &
FRONTEND_PID=$!
wait_for "http://localhost:3000" "frontend" 45 "$FRONTEND_PID"

# ---- status lines ----
echo
if probe "http://localhost:8000/health"; then
  echo "[OK]   backend   running (pid $BACKEND_PID)  http://localhost:8000/health"
else
  echo "[FAIL] backend   not answering at http://localhost:8000/health"
fi
if kill -0 "$SCHEDULER_PID" 2>/dev/null; then
  echo "[OK]   scheduler running (pid $SCHEDULER_PID)  python -m app.scheduler"
else
  echo "[FAIL] scheduler not running - see its error messages above (the app still works, but no background refresh / alerts)"
fi
if probe "http://localhost:3000"; then
  echo "[OK]   frontend  running (pid $FRONTEND_PID)  http://localhost:3000"
else
  echo "[FAIL] frontend  not answering at http://localhost:3000"
fi
echo
echo "Open http://localhost:3000 . Press Ctrl+C to stop all three."

# Block until a child exits or Ctrl+C; the EXIT trap then stops the rest.
wait || true

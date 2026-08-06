#!/usr/bin/env bash
# One-command local dev launcher for stock-desk (backend + frontend).
# Run from anywhere inside the repo: `bash apps/stock-desk/dev-up.sh`.
# Backend MUST be started from its own directory so the default SQLite path
# (./data/stock-desk.db) always resolves to the same database file.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BACKEND_DIR="$REPO_ROOT/apps/stock-desk/backend"
FRONTEND_DIR="$REPO_ROOT/apps/stock-desk/frontend"

echo "==> Pulling latest product/stock-desk"
git -C "$REPO_ROOT" pull origin product/stock-desk

echo "==> Starting backend on :8000"
(cd "$BACKEND_DIR" && uv run uvicorn app.main:app --reload --port 8000) &
BACKEND_PID=$!

# Stop both processes together on Ctrl+C / script exit.
trap 'kill "$BACKEND_PID" 2>/dev/null || true' EXIT

echo "==> Starting frontend on :3000 (Ctrl+C stops both)"
cd "$FRONTEND_DIR" && npm run dev

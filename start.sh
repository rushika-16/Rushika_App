#!/usr/bin/env bash
set -euo pipefail

cd /app

python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 &
backend_pid=$!

cleanup() {
  kill "$backend_pid" 2>/dev/null || true
}

trap cleanup EXIT INT TERM

export BACKEND_URL="${BACKEND_URL:-http://127.0.0.1:8000}"

exec python -m streamlit run frontend/app.py --server.address 0.0.0.0 --server.port "${PORT:-7860}"

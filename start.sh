#!/usr/bin/env bash
set -euo pipefail

cd /app

python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 &

exec python -m streamlit run frontend/app.py --server.address 0.0.0.0 --server.port "${PORT:-7860}"
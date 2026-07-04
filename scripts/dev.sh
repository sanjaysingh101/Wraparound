#!/usr/bin/env bash
# Run backend (FastAPI :7345) and frontend (Vite :5173) together for development.
set -euo pipefail
cd "$(dirname "$0")/.."

trap 'kill 0' EXIT

(cd backend && .venv/bin/python -m wraparound) &
(cd app && npm run dev) &
wait

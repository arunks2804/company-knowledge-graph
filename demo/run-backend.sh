#!/usr/bin/env bash
# Start the API for the demo with demo/demo.env. Set PYTHON to a venv that has backend/requirements.txt.
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; source demo/demo.env; set +a
# auth.json holds the demo admin; keep it separate from any real backend/config/auth.json
export AUTH_STORE_PATH="${AUTH_STORE_PATH:-$PWD/demo/.auth.demo.json}"
cd backend
exec "${PYTHON:-python3}" -m uvicorn app.main:app --host 127.0.0.1 --port 8007

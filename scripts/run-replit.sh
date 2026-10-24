#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

API_PORT="${API_PORT:-8000}"
DASHBOARD_PORT="${DASHBOARD_PORT:-8501}"

if [[ -f "$ROOT/.venv/bin/activate" ]]; then
    source "$ROOT/.venv/bin/activate"
fi

export DATABASE_URL="${DATABASE_URL:-sqlite:///$ROOT/data/inventory.db}"
export FORECAST_PACKAGE_ROOT="${FORECAST_PACKAGE_ROOT:-$ROOT/src}"
export FORECAST_ENGINE="${FORECAST_ENGINE:-baseline}"
export AUTO_SEED_DEMO="${AUTO_SEED_DEMO:-true}"
export API_BASE_URL="${API_BASE_URL:-http://127.0.0.1:$API_PORT/api/v1}"

API_PID=""
DASHBOARD_PID=""
cleanup() {
    for pid in "$DASHBOARD_PID" "$API_PID"; do
        if [[ -n "$pid" ]]; then
            kill "$pid" 2>/dev/null || true
        fi
    done
}
trap cleanup EXIT INT TERM

(
    cd "$ROOT/src/backend"
    PORT="$API_PORT" exec python -m scripts.start
) &
API_PID=$!

streamlit run "$ROOT/src/dashboard/app.py" \
    --server.address=0.0.0.0 \
    --server.port="$DASHBOARD_PORT" \
    --server.headless=true &
DASHBOARD_PID=$!

wait "$DASHBOARD_PID"

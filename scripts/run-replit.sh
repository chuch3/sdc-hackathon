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
cleanup() {
    if [[ -n "$API_PID" ]]; then
        kill "$API_PID" 2>/dev/null || true
    fi
}
trap cleanup EXIT INT TERM

(
    cd "$ROOT/src/backend"
    PORT="$API_PORT" exec python -m scripts.start
) &
API_PID=$!

API_HEALTHY=0
for _ in $(seq 1 60); do
    if python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:$API_PORT/health', timeout=1)" 2>/dev/null; then
        API_HEALTHY=1
        break
    fi
    sleep 1
done
if [[ "$API_HEALTHY" -ne 1 ]]; then
    echo "FreshStock API did not become healthy on port $API_PORT." >&2
    exit 1
fi

streamlit run "$ROOT/src/dashboard/app.py" \
    --server.address=0.0.0.0 \
    --server.port="$DASHBOARD_PORT" \
    --server.headless=true

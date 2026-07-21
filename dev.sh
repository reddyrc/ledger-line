#!/usr/bin/env bash
# Start Ledgerline API (:8000) + React UI (:5180) together.
# Usage:
#   ./dev.sh           # start both (frees 8000/5180 if occupied)
#   ./dev.sh --stop    # stop whatever is on those ports
#   ./dev.sh --status  # show what's listening

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
API_PORT="${API_PORT:-8000}"
WEB_PORT="${WEB_PORT:-5180}"
API_PID_FILE="${ROOT}/.dev-api.pid"
WEB_PID_FILE="${ROOT}/.dev-web.pid"
LOG_DIR="${ROOT}/.dev-logs"

mkdir -p "${LOG_DIR}"

red() { printf '\033[31m%s\033[0m\n' "$*"; }
green() { printf '\033[32m%s\033[0m\n' "$*"; }
dim() { printf '\033[2m%s\033[0m\n' "$*"; }

pids_on_port() {
  local port="$1"
  lsof -nP -iTCP:"${port}" -sTCP:LISTEN -t 2>/dev/null | sort -u || true
}

kill_port() {
  local port="$1"
  local pids
  pids="$(pids_on_port "${port}")"
  if [[ -z "${pids}" ]]; then
    return 0
  fi
  echo "Freeing port ${port} (PIDs: $(echo "${pids}" | tr '\n' ' '))"
  # shellcheck disable=SC2086
  kill ${pids} 2>/dev/null || true
  sleep 0.4
  pids="$(pids_on_port "${port}")"
  if [[ -n "${pids}" ]]; then
    # shellcheck disable=SC2086
    kill -9 ${pids} 2>/dev/null || true
  fi
}

stop_all() {
  echo "Stopping Ledgerline dev processes..."
  if [[ -f "${API_PID_FILE}" ]]; then
    kill "$(cat "${API_PID_FILE}")" 2>/dev/null || true
    rm -f "${API_PID_FILE}"
  fi
  if [[ -f "${WEB_PID_FILE}" ]]; then
    kill "$(cat "${WEB_PID_FILE}")" 2>/dev/null || true
    rm -f "${WEB_PID_FILE}"
  fi
  kill_port "${API_PORT}"
  kill_port "${WEB_PORT}"
  green "Stopped."
}

status() {
  echo "API :${API_PORT} -> $(pids_on_port "${API_PORT}" | tr '\n' ' ' || echo '(free)')"
  echo "UI  :${WEB_PORT} -> $(pids_on_port "${WEB_PORT}" | tr '\n' ' ' || echo '(free)')"
  if curl -sf "http://127.0.0.1:${API_PORT}/api/v1/health" >/dev/null 2>&1; then
    green "API health: ok"
  else
    dim "API health: not responding"
  fi
  if curl -sf "http://127.0.0.1:${WEB_PORT}/" >/dev/null 2>&1; then
    green "UI health: ok -> http://localhost:${WEB_PORT}"
  else
    dim "UI health: not responding"
  fi
}

ensure_backend() {
  if [[ ! -d "${ROOT}/.venv" ]]; then
    echo "Creating Python venv..."
    python3 -m venv "${ROOT}/.venv"
  fi
  # shellcheck disable=SC1091
  source "${ROOT}/.venv/bin/activate"
  if ! python -c "import fastapi, uvicorn, yfinance" 2>/dev/null; then
    echo "Installing Python dependencies..."
    pip install -q -r "${ROOT}/requirements.txt"
  fi
  if [[ ! -f "${ROOT}/.env" && -f "${ROOT}/.env.example" ]]; then
    cp "${ROOT}/.env.example" "${ROOT}/.env"
    dim "Created .env from .env.example - set SEC_USER_AGENT to your email."
  fi
}

ensure_frontend() {
  if [[ ! -d "${ROOT}/web/node_modules" ]]; then
    echo "Installing frontend dependencies..."
    (cd "${ROOT}/web" && npm install)
  fi
  if [[ ! -f "${ROOT}/web/.env" && -f "${ROOT}/web/.env.example" ]]; then
    cp "${ROOT}/web/.env.example" "${ROOT}/web/.env"
  fi
  # Keep UI pointed at the API port we start
  if grep -q '^VITE_API_URL=' "${ROOT}/web/.env" 2>/dev/null; then
    sed -i.bak "s|^VITE_API_URL=.*|VITE_API_URL=http://localhost:${API_PORT}/api/v1|" "${ROOT}/web/.env"
    rm -f "${ROOT}/web/.env.bak"
  else
    echo "VITE_API_URL=http://localhost:${API_PORT}/api/v1" >>"${ROOT}/web/.env"
  fi
}

wait_for() {
  local url="$1"
  local name="$2"
  local tries=40
  local i=0
  while (( i < tries )); do
    if curl -sf "${url}" >/dev/null 2>&1; then
      green "${name} ready"
      return 0
    fi
    sleep 0.25
    i=$((i + 1))
  done
  red "${name} did not become ready: ${url}"
  return 1
}

cleanup() {
  echo
  dim "Shutting down..."
  stop_all
  exit 0
}

start_all() {
  ensure_backend
  ensure_frontend

  # Always free the ports so restart is one command
  kill_port "${API_PORT}"
  kill_port "${WEB_PORT}"

  # shellcheck disable=SC1091
  source "${ROOT}/.venv/bin/activate"
  export PYTHONPATH="${ROOT}/src"

  echo "Starting API on :${API_PORT}..."
  (
    cd "${ROOT}"
    exec uvicorn finance_app.main:app --reload --host 127.0.0.1 --port "${API_PORT}"
  ) >"${LOG_DIR}/api.log" 2>&1 &
  echo $! >"${API_PID_FILE}"

  echo "Starting UI on :${WEB_PORT}..."
  (
    cd "${ROOT}/web"
    exec npm run dev -- --host 127.0.0.1 --port "${WEB_PORT}"
  ) >"${LOG_DIR}/web.log" 2>&1 &
  echo $! >"${WEB_PID_FILE}"

  wait_for "http://127.0.0.1:${API_PORT}/api/v1/health" "API"
  wait_for "http://127.0.0.1:${WEB_PORT}/" "UI"

  echo
  green "Ledgerline is running"
  echo "  UI  -> http://localhost:${WEB_PORT}"
  echo "  API -> http://localhost:${API_PORT}/docs"
  echo "  Try -> http://localhost:${WEB_PORT}/s/INTC"
  dim "  Logs -> ${LOG_DIR}/api.log , ${LOG_DIR}/web.log"
  dim "  Stop -> Ctrl+C  or  ./dev.sh --stop"
  echo

  trap cleanup INT TERM
  # Keep script alive while children run
  while kill -0 "$(cat "${API_PID_FILE}")" 2>/dev/null \
    && kill -0 "$(cat "${WEB_PID_FILE}")" 2>/dev/null; do
    sleep 1
  done
  red "A process exited unexpectedly - check logs in ${LOG_DIR}"
  stop_all
  exit 1
}

case "${1:-}" in
  --stop | stop)
    stop_all
    ;;
  --status | status)
    status
    ;;
  --help | -h | help)
    cat <<EOF
Usage: ./dev.sh [--stop|--status]

Starts the FastAPI backend and Vite frontend together.
Frees ports ${API_PORT} / ${WEB_PORT} if they are already in use.

Env overrides:
  API_PORT=8001 WEB_PORT=5181 ./dev.sh
EOF
    ;;
  "")
    start_all
    ;;
  *)
    red "Unknown option: $1"
    exit 1
    ;;
esac

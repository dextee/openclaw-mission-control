#!/usr/bin/env bash
# Start the local Caddy reverse proxy + ngrok tunnel that exposes
# Mission Control over HTTPS.
#
# Caddy listens on :18080 and proxies /api/* -> backend:8000 and / -> frontend:3000
# (see ops/Caddyfile.ngrok). ngrok then tunnels :18080 to a public URL.
#
# Idempotent: existing caddy/ngrok processes for this setup are killed first.
#
# Usage:
#   scripts/start_ngrok_proxy.sh           # start (or restart) both
#   scripts/start_ngrok_proxy.sh --stop    # stop both
#   scripts/start_ngrok_proxy.sh --status  # print public URL + caddy/ngrok pids

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CADDYFILE="${REPO_ROOT}/ops/Caddyfile.ngrok"
CADDY_LOG="/tmp/caddy-ngrok.log"
NGROK_LOG="/tmp/ngrok-mc.log"
PROXY_PORT="${PROXY_PORT:-18080}"

cmd_status() {
  echo "--- Caddy ---"
  pgrep -af "caddy run --config ${CADDYFILE}" || echo "  (not running)"
  echo "--- ngrok ---"
  pgrep -af "ngrok http ${PROXY_PORT}" || echo "  (not running)"
  echo "--- Public URL ---"
  curl -s --max-time 2 http://localhost:4040/api/tunnels \
    | python3 -c 'import sys,json; d=json.load(sys.stdin); [print(t["public_url"]) for t in d.get("tunnels",[])]' \
    2>/dev/null || echo "  (ngrok admin API not reachable)"
}

cmd_stop() {
  pkill -f "caddy run --config ${CADDYFILE}" 2>/dev/null || true
  pkill -f "ngrok http ${PROXY_PORT}" 2>/dev/null || true
  echo "Stopped caddy + ngrok."
}

cmd_start() {
  if [ ! -f "${CADDYFILE}" ]; then
    echo "Missing ${CADDYFILE}" >&2
    exit 1
  fi
  if ! command -v caddy >/dev/null 2>&1; then
    echo "caddy is not installed (apt install caddy or fetch from caddyserver.com)" >&2
    exit 1
  fi
  if ! command -v ngrok >/dev/null 2>&1; then
    echo "ngrok is not installed (https://ngrok.com/download)" >&2
    exit 1
  fi

  cmd_stop
  sleep 1

  echo "Starting caddy on :${PROXY_PORT} (log: ${CADDY_LOG})"
  nohup caddy run --config "${CADDYFILE}" >"${CADDY_LOG}" 2>&1 &

  echo "Starting ngrok http ${PROXY_PORT} (log: ${NGROK_LOG})"
  nohup ngrok http "${PROXY_PORT}" >"${NGROK_LOG}" 2>&1 &

  # Wait for ngrok admin API to come up.
  for _ in 1 2 3 4 5 6 7 8 9 10; do
    if curl -s --max-time 2 http://localhost:4040/api/tunnels >/dev/null 2>&1; then
      break
    fi
    sleep 1
  done

  cmd_status
}

case "${1:-start}" in
  start) cmd_start ;;
  stop) cmd_stop ;;
  status) cmd_status ;;
  *)
    echo "Usage: $0 [start|stop|status]" >&2
    exit 1
    ;;
esac

#!/usr/bin/env bash
# Boot smoke test: starts the real API, waits for it and calls /health (liveness) and /ready (readiness).
#
# Configuration (all optional, via environment):
#   SMOKE_PORT             port the API listens on                                  (default 18000)
#   SMOKE_TIMEOUT          seconds to wait for the API to come up                   (default 30)
#   SMOKE_ENV_FILE         file with the environment the API boots with             (default .env.example)
#   SMOKE_ENV              value of ENV, to mimic production                        (default production)
#   SMOKE_COMPOSE_FILE     compose file with dependencies (Postgres...) to start    (default: none)
#   SMOKE_MIGRATE_COMMAND  command that migrates the empty database                 (default: none)
#
# Adapting to your project: see "Boot smoke test" in the README.
set -euo pipefail

cd "$(dirname "$0")/.."

PORT="${SMOKE_PORT:-18000}"
TIMEOUT="${SMOKE_TIMEOUT:-30}"
ENV_FILE="${SMOKE_ENV_FILE:-.env.example}"
BASE_URL="http://127.0.0.1:${PORT}"
COMPOSE_FILE="${SMOKE_COMPOSE_FILE:-}"
LOG_FILE="$(mktemp -t smoke-api.XXXXXX.log)"
API_PID=""
COMPOSE_UP=0

cleanup() {
  local status=$?
  if [ -n "$API_PID" ] && kill -0 "$API_PID" 2>/dev/null; then
    kill -- "-$API_PID" 2>/dev/null || kill "$API_PID" 2>/dev/null || true
    wait "$API_PID" 2>/dev/null || true
  fi
  if [ "$COMPOSE_UP" -eq 1 ]; then
    docker compose -f "$COMPOSE_FILE" down --volumes --remove-orphans || true
  fi
  if [ "$status" -ne 0 ] && [ -s "$LOG_FILE" ]; then
    echo ">> smoke FAILED. API logs:" >&2
    cat "$LOG_FILE" >&2
  fi
  rm -f "$LOG_FILE"
  exit "$status"
}
trap cleanup EXIT INT TERM

# EPOCHREALTIME needs bash 5; older bash (macOS) falls back to whole seconds
now_us() {
  if [ -n "${EPOCHREALTIME:-}" ]; then
    echo "${EPOCHREALTIME/[.,]/}"
    return
  fi
  echo $((SECONDS * 1000000))
}

fail() {
  echo ">> smoke: $*" >&2
  exit 1
}

# Loads KEY=VALUE lines literally (sourcing would mangle values such as JSON lists)
while IFS= read -r line || [ -n "$line" ]; do
  case "$line" in
    '' | '#'*) continue ;;
  esac
  export "${line%%=*}=${line#*=}"
done <"$ENV_FILE"
export ENV="${SMOKE_ENV:-production}"

if [ -n "$COMPOSE_FILE" ]; then
  echo ">> starting dependencies ($COMPOSE_FILE)"
  COMPOSE_UP=1
  docker compose -f "$COMPOSE_FILE" up --detach --wait
fi

if [ -n "${SMOKE_MIGRATE_COMMAND:-}" ]; then
  echo ">> running migrations"
  bash -c "$SMOKE_MIGRATE_COMMAND"
fi
# Alembic example: SMOKE_MIGRATE_COMMAND="uv run --no-dev alembic upgrade head"

echo ">> starting the API on ${BASE_URL} (ENV=${ENV})"
# setsid gives the API its own process group so cleanup also stops uv's child process
setsid uv run --no-dev uvicorn app.main.main:app --host 127.0.0.1 --port "$PORT" >"$LOG_FILE" 2>&1 &
API_PID=$!

BOOT_STARTED_US="$(now_us)"
echo ">> waiting for /health (up to ${TIMEOUT}s)"
deadline=$((SECONDS + TIMEOUT))
until curl --silent --fail --output /dev/null "${BASE_URL}/health"; do
  kill -0 "$API_PID" 2>/dev/null || fail "the API process exited before becoming healthy"
  [ "$SECONDS" -lt "$deadline" ] || fail "the API did not become healthy within ${TIMEOUT}s"
  sleep 0.5
done

boot_ms=$((($(now_us) - BOOT_STARTED_US) / 1000))
printf '>> API healthy after %d.%03ds\n' $((boot_ms / 1000)) $((boot_ms % 1000))

check_endpoint() {
  local path="$1" body
  body="$(curl --silent --show-error --fail-with-body "${BASE_URL}${path}")" || fail "GET ${path} failed: ${body:-no response}"
  echo ">> GET ${path} -> ${body}"
}

check_endpoint /health
check_endpoint /ready

echo ">> smoke OK"

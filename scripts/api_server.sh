# Shared boot of the real API, sourced by scripts/smoke.sh and scripts/contract.sh (not executable).
# Loads the environment file, starts the dependencies, runs the migrations, starts uvicorn and waits for
# /health. On exit it always stops everything and, on failure, prints the API logs.
#
# Configuration (all optional, via environment):
#   SMOKE_PORT             port the API listens on                                  (default 18000)
#   SMOKE_TIMEOUT          seconds to wait for the API to come up                   (default 30)
#   SMOKE_ENV_FILE         file with the environment the API boots with             (default .env.example)
#   SMOKE_ENV              value of ENV, to mimic production                        (default production)
#   SMOKE_COMPOSE_FILE     compose file with dependencies (Postgres...) to start    (default: none)
#   SMOKE_MIGRATE_COMMAND  command that migrates the empty database                 (default: none)
#
# The sourcing script sets API_LABEL (used in the messages) and must run from the repository root.

PORT="${SMOKE_PORT:-18000}"
TIMEOUT="${SMOKE_TIMEOUT:-30}"
ENV_FILE="${SMOKE_ENV_FILE:-.env.example}"
BASE_URL="http://127.0.0.1:${PORT}"
COMPOSE_FILE="${SMOKE_COMPOSE_FILE:-}"
API_LABEL="${API_LABEL:-smoke}"
LOG_FILE="$(mktemp -t "${API_LABEL}-api.XXXXXX.log")"
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
    echo ">> ${API_LABEL} FAILED. API logs:" >&2
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
  echo ">> ${API_LABEL}: $*" >&2
  exit 1
}

# Loads KEY=VALUE lines literally (sourcing would mangle values such as JSON lists)
load_env_file() {
  local line
  while IFS= read -r line || [ -n "$line" ]; do
    case "$line" in
      '' | '#'*) continue ;;
    esac
    export "${line%%=*}=${line#*=}"
  done <"$ENV_FILE"
  export ENV="${SMOKE_ENV:-production}"
}

start_dependencies() {
  [ -n "$COMPOSE_FILE" ] || return 0
  echo ">> starting dependencies ($COMPOSE_FILE)"
  COMPOSE_UP=1
  docker compose -f "$COMPOSE_FILE" up --detach --wait
}

# Alembic example: SMOKE_MIGRATE_COMMAND="uv run --no-dev alembic upgrade head"
run_migrations() {
  [ -n "${SMOKE_MIGRATE_COMMAND:-}" ] || return 0
  echo ">> running migrations"
  bash -c "$SMOKE_MIGRATE_COMMAND"
}

start_api() {
  echo ">> starting the API on ${BASE_URL} (ENV=${ENV})"
  # setsid gives the API its own process group so cleanup also stops uv's child process
  setsid uv run --no-dev uvicorn app.main.main:app --host 127.0.0.1 --port "$PORT" >"$LOG_FILE" 2>&1 &
  API_PID=$!
}

wait_for_health() {
  local started_us deadline boot_ms
  started_us="$(now_us)"
  echo ">> waiting for /health (up to ${TIMEOUT}s)"
  deadline=$((SECONDS + TIMEOUT))
  until curl --silent --fail --output /dev/null "${BASE_URL}/health"; do
    kill -0 "$API_PID" 2>/dev/null || fail "the API process exited before becoming healthy"
    [ "$SECONDS" -lt "$deadline" ] || fail "the API did not become healthy within ${TIMEOUT}s"
    sleep 0.5
  done
  boot_ms=$((($(now_us) - started_us) / 1000))
  printf '>> API healthy after %d.%03ds\n' $((boot_ms / 1000)) $((boot_ms % 1000))
}

boot_api() {
  load_env_file
  start_dependencies
  run_migrations
  start_api
  wait_for_health
}

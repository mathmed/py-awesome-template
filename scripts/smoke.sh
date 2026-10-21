#!/usr/bin/env bash
# Boot smoke test: starts the real API, waits for it and calls /health (liveness) and /ready (readiness).
#
# The boot (environment file, dependencies, migrations, uvicorn) lives in scripts/api_server.sh, shared
# with scripts/contract.sh; its header lists the SMOKE_* options.
#
# Adapting to your project: see "Boot smoke test" in the README.
set -euo pipefail

cd "$(dirname "$0")/.."

API_LABEL=smoke
# shellcheck source=scripts/api_server.sh
source scripts/api_server.sh

boot_api

check_endpoint() {
  local path="$1" body
  body="$(curl --silent --show-error --fail-with-body --max-time "$HTTP_TIMEOUT_SECONDS" "${BASE_URL}${path}")" || fail "GET ${path} failed: ${body:-no response}"
  echo ">> GET ${path} -> ${body}"
}

check_endpoint /health
check_endpoint /ready

echo ">> smoke OK"

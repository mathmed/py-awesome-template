#!/usr/bin/env bash
# API contract test: boots the real API exactly like scripts/smoke.sh and runs a bounded, deterministic
# Schemathesis pass against its OpenAPI schema (/openapi.json): every response must match the documented
# status codes, content types, headers and schemas, invalid input must be rejected and nothing may answer
# with a 5xx.
#
# Configuration (all optional, via environment), plus the SMOKE_* options in scripts/api_server.sh:
#   CONTRACT_MAX_EXAMPLES    test cases generated per operation and phase      (default 50)
#   CONTRACT_SEED            seed of the data generation                       (default 1)
#   CONTRACT_REQUEST_TIMEOUT seconds before a single request counts as failed  (default 5)
#
# Extra arguments go straight to `schemathesis run`, e.g. authentication for protected routes:
#   ./scripts/contract.sh --header "Authorization: Bearer ${CONTRACT_TOKEN}"
set -euo pipefail

cd "$(dirname "$0")/.."

API_LABEL=contract
# shellcheck source=scripts/api_server.sh
source scripts/api_server.sh

MAX_EXAMPLES="${CONTRACT_MAX_EXAMPLES:-50}"
SEED="${CONTRACT_SEED:-1}"
REQUEST_TIMEOUT="${CONTRACT_REQUEST_TIMEOUT:-5}"

boot_api

echo ">> running schemathesis against ${BASE_URL}/openapi.json (seed ${SEED}, max ${MAX_EXAMPLES} examples)"
# One worker, a fixed seed and no example database: the same code always produces the same requests, so
# a CI failure is reproducible locally with `make contract` (change CONTRACT_SEED to explore other inputs).
uv run --locked schemathesis run "${BASE_URL}/openapi.json" \
  --checks all \
  --workers 1 \
  --seed "$SEED" \
  --generation-database none \
  --max-examples "$MAX_EXAMPLES" \
  --request-timeout "$REQUEST_TIMEOUT" \
  --no-color \
  "$@" || fail "schemathesis failed: contract violations or invalid options, see its output above"

echo ">> contract OK"

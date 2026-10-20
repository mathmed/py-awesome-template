# Base branch used by mutation-changed and openapi-diff
BASE ?= origin/main

.PHONY: setup dev dev-build run build test test-unit hooks check-code format-code smoke lint-imports mutation mutation-changed mutation-results suppressions suppressions-update contract openapi-diff risk-labels

# Install uv (if missing), project dependencies and git hooks
setup:
	@command -v uv >/dev/null 2>&1 || { \
		echo ">> installing uv"; \
		curl -LsSf https://astral.sh/uv/install.sh | sh; \
	}
	@echo ">> uv: $$(uv --version)"
	uv sync
	@[ -f .env ] || { cp .env.example .env && echo ">> created .env from .env.example"; }
	uv run pre-commit install

# Start project in development mode (docker)
dev:
	docker compose --env-file=.env -f ./docker/docker-compose.yaml up

# Start project in development mode with rebuild (docker)
dev-build:
	docker compose --env-file=.env -f ./docker/docker-compose.yaml up --build

# Build the production docker image
build:
	docker build --target production -t py-awesome-template -f docker/Dockerfile .

# Start project locally without docker
run:
	uv run uvicorn app.main.main:app --reload --host 0.0.0.0 --port 8000

# Run all tests with coverage
test:
	uv run pytest --cov --cov-report=term-missing

# Run only the fast unit tests
test-unit:
	uv run pytest tests/unit

# Run all quality checks (ruff, mypy, bandit, vulture, xenon, import-linter, suppressions, pip-audit)
hooks:
	uv run pre-commit run --all-files

# Lint and check formatting
check-code:
	uv run ruff check . && uv run ruff format --check .

# Fix lint issues and format code
format-code:
	uv run ruff check --fix . && uv run ruff format .

# Boot the real API and call /health and /ready (see scripts/smoke.sh for the options)
smoke:
	./scripts/smoke.sh

# Boot the real API and run a bounded, deterministic Schemathesis pass against its OpenAPI schema
contract:
	./scripts/contract.sh

# Fail on breaking changes between the OpenAPI schema of HEAD and of BASE (needs oasdiff, see the README)
openapi-diff:
	uv run python scripts/openapi.py diff --base $(BASE)

# Check the architecture contracts in pyproject.toml ([tool.importlinter])
lint-imports:
	uv run lint-imports

# Mutation testing of the whole domain (slow, see README); results: make mutation-results
mutation:
	uv run mutmut run
	uv run python scripts/mutation.py report

# Mutation testing only of the domain files changed against BASE (what the PR job runs)
mutation-changed:
	uv run python scripts/mutation.py changed --base $(BASE)

mutation-results:
	uv run mutmut results

# Fail when the suppressions (noqa, type: ignore, nosec, skip...) differ from suppressions-baseline.json
suppressions:
	uv run python scripts/suppressions.py check

# Lower the baseline after removing suppressions (refuses to raise it, see the README)
suppressions-update:
	uv run python scripts/suppressions.py update

# Create (or update) the risk:<level> labels on the GitHub repository (needs an authenticated gh)
risk-labels:
	gh label create "risk:low" --color 0E8A16 --description "Low risk: routine change" --force
	gh label create "risk:medium" --color FBCA04 --description "Medium risk: deploy steps or wider impact" --force
	gh label create "risk:high" --color D93F0B --description "High risk: pipeline config, migrations, auth or core rules" --force
	gh label create "risk:critical" --color B60205 --description "Critical risk: needs the closest review" --force

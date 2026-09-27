.PHONY: setup dev dev-build run build test hooks check-code format-code

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

# Run unit tests with coverage
test:
	uv run pytest --cov --cov-report=term-missing

# Run all quality checks (ruff, mypy, bandit, vulture, xenon, pip-audit)
hooks:
	uv run pre-commit run --all-files

# Lint and check formatting
check-code:
	uv run ruff check . && uv run ruff format --check .

# Fix lint issues and format code
format-code:
	uv run ruff check --fix . && uv run ruff format .

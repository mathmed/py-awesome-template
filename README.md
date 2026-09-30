# py-awesome-template

[![CI](https://github.com/mathmed/py-awesome-template/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/mathmed/py-awesome-template/actions/workflows/ci.yml)
[![Coverage](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/mathmed/py-awesome-template/python-coverage-comment-action-data/endpoint.json)](https://htmlpreview.github.io/?https://github.com/mathmed/py-awesome-template/blob/python-coverage-comment-action-data/htmlcov/index.html)
[![Python 3.14](https://img.shields.io/badge/python-3.14-blue?logo=python&logoColor=white)](https://www.python.org/)
[![Checked with mypy](https://www.mypy-lang.org/static/mypy_badge.svg)](https://mypy-lang.org/)
[![Security: bandit](https://img.shields.io/badge/security-bandit-yellow.svg)](https://github.com/PyCQA/bandit)
[![Dependabot](https://img.shields.io/badge/dependabot-enabled-025E8C?logo=dependabot)](.github/dependabot.yaml)

A production-ready starting point for Python 3.14 APIs with FastAPI: a layered folder structure, modern tooling with [uv](https://docs.astral.sh/uv/) and [ruff](https://docs.astral.sh/ruff/), quality gates in pre-commit and CI, and Docker for development and production.

## Features

- **Layered structure**: domain, infra and presentation layers, with the domain isolated from frameworks through contracts.
- **Quality tooling**: ruff (lint + format), mypy (types), bandit (security), vulture (dead code), xenon (complexity), import-linter (architecture contracts) and pip-audit (vulnerable dependencies), all in [pre-commit](https://pre-commit.com/) hooks.
- **Tests**: pytest with unit and integration suites and an 80% coverage gate.
- **CI**: every pull request runs all checks and posts coverage and quality reports as comments.
- **Dependabot**: weekly grouped updates for Python dependencies and GitHub Actions.
- **Production basics**: typed settings ([pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)), JSON logs in production, configurable CORS, domain errors mapped to HTTP status codes and `/health` (liveness) and `/ready` (readiness) routes.
- **Deterministic validation for AI-generated code**: a boot smoke test, architecture contracts and mutation testing (see [Validation layers](#validation-layers)).
- **Docker**: a `dev` stage with hot reload and a slim, non-root `production` stage with healthcheck.
- **AI-ready**: `CLAUDE.md`/`AGENTS.md` with the project rules, Claude Code agents (`coder`, `reviewer`), permissions and a hook that formats every file the agent edits.

## Getting started

```sh
make setup   # installs uv if missing, dependencies (and Python 3.14), .env and git hooks
make run     # starts the API at http://localhost:8000 (docs at /docs)
```

Or run it with Docker: `make dev` (the port is `APP_PORT` from `.env`).

```sh
curl http://localhost:8000/health
curl http://localhost:8000/ready
curl "http://localhost:8000/example?field1=hello"
```

### Commands

| Command            | Description                                                             |
| ------------------ | ----------------------------------------------------------------------- |
| `make setup`       | Install uv, project dependencies and git hooks.                         |
| `make run`         | Run the API locally with hot reload.                                    |
| `make dev`         | Run the API with Docker (`make dev-build` to rebuild the image).        |
| `make build`       | Build the production Docker image.                                      |
| `make test`        | Run all tests with coverage.                                            |
| `make test-unit`   | Run only the unit tests.                                                |
| `make hooks`       | Run all quality checks (ruff, mypy, bandit, vulture, xenon, import-linter, pip-audit). |
| `make smoke`       | Boot the real API and call `/health` and `/ready`.                      |
| `make lint-imports` | Check the architecture contracts (import-linter).                      |
| `make mutation`    | Mutation testing of the domain (slow); `make mutation-results` lists survivors. |
| `make check-code`  | Lint and check formatting with ruff.                                    |
| `make format-code` | Fix lint issues and format the code with ruff.                          |

### Dependencies

Use `uv add <package>` for production dependencies and `uv add --dev <package>` for development ones. Always commit `uv.lock`.

### Environment variables

Loaded from the environment or the `.env` file by `app/common/settings.py`. New variables go there and in `.env.example`.

| Variable       | Default       | Description                                                     |
| -------------- | ------------- | --------------------------------------------------------------- |
| `APP_PORT`     | -             | Host port used by `make dev`.                                   |
| `ENV`          | `development` | `development`, `test` or `production`. Production logs JSON.    |
| `LOG_LEVEL`    | `INFO`        | Python logging level.                                           |
| `CORS_ORIGINS` | `[]`          | JSON list of allowed origins, e.g. `["http://localhost:3000"]`. |

## Validation layers

Tests written by an AI agent can pass and still prove little. Three deterministic layers catch what line coverage does not.

### Boot smoke test (`make smoke`)

`scripts/smoke.sh` boots the API for real (uvicorn, `ENV=production`, environment loaded from `.env.example`), waits for `/health` with a timeout, then calls `/health` (liveness: touches no dependency) and `/ready` (readiness: runs the checks of every real dependency, returns `503` if any is down). On failure it prints the API logs; on exit it always stops everything. It runs in CI as the `smoke` job and blocks the PR.

The template has no database, so `/ready` reports `{"status": "ready", "dependencies": []}`. To adapt it to your project:

1. **Add a dependency check**: implement `ReadinessCheckContract` in `app/infra/` (e.g. a `SELECT 1` on Postgres, catching the driver's specific exceptions and returning `False`) and register it in `app/presentation/factories/check_readiness_factory.py`.
2. **Start the dependencies**: create a compose file with them (e.g. `docker/docker-compose.smoke.yaml` with a Postgres and a `healthcheck`) and run `SMOKE_COMPOSE_FILE=docker/docker-compose.smoke.yaml make smoke`. Make it the default in the script if you want. In CI, use `services:` in the `smoke` job (an example is commented in `ci.yml`).
3. **Run migrations on an empty database**: set `SMOKE_MIGRATE_COMMAND`, e.g. `uv run --no-dev alembic upgrade head`.
4. **Point the app at the dependencies**: put the variables (e.g. `DATABASE_URL`) in `.env.example`; the smoke test boots with exactly that file (`SMOKE_ENV_FILE` picks another one), so no test-only environment hides a broken configuration.

Other options: `SMOKE_PORT` (default `18000`), `SMOKE_TIMEOUT` (default `30` seconds) and `SMOKE_ENV` (default `production`).

### Architecture contracts (`make lint-imports`)

[import-linter](https://import-linter.readthedocs.io/) contracts in `pyproject.toml` (`[tool.importlinter]`) mirror the architecture rules: layers (`main > presentation > infra > domain`), the domain not importing `infra`, `presentation`, `common`, `main` or web/ORM/HTTP frameworks, layers inside the domain, and independence between use case features and between infra integrations. It runs as a pre-commit hook, in `make hooks` and as the `lint-imports` CI job.

To add a contract, append a block to `pyproject.toml` and run `make lint-imports`:

```toml
[[tool.importlinter.contracts]]
name = "Billing does not depend on shipping"
type = "forbidden"            # or "layers" / "independence"
source_modules = ["app.domain.usecases.billing"]
forbidden_modules = ["app.domain.usecases.shipping"]
```

When a contract breaks, fix the import. Only relax a contract (or add `ignore_imports`) as a deliberate architecture decision, never to make a check pass.

### Mutation testing (`make mutation`)

[mutmut](https://mutmut.readthedocs.io/) changes the domain code (flips a `>` into `>=`, drops an argument, negates a condition...) and runs the tests against each change. A test suite that still passes has a **surviving mutant**: that line is executed but its behaviour is not asserted. Coverage says the line ran; mutation testing says whether a test would notice if it were wrong.

The scope is `app/domain` (use cases and business rules, `[tool.mutmut]` in `pyproject.toml`); infra, presentation, main and common are covered by integration tests and left out. It is slow, so it does not gate PRs: the `Mutation testing` workflow runs weekly and on demand (`workflow_dispatch`) and writes the result in the run summary.

Reading the result:

```sh
make mutation           # runs; the summary shows killed (🎉) and survived (🙁) mutants
make mutation-results   # lists the survivors
uv run mutmut show <name>   # diff of a surviving mutant: what changed and no test noticed
```

Score per module = killed ÷ total mutants. For each survivor, either add the missing assertion, or, if the mutant does not change behaviour (an equivalent mutant), leave it. Don't lower the scope to raise the score.

## Folder structure

```
app/
├── common/                 # Cross-cutting code usable by any layer: settings and logging
├── domain/                 # Business core, framework-free
│   ├── constants/
│   ├── enums/
│   ├── errors/             # Domain errors (NotFoundError, ConflictError...)
│   ├── contracts/          # Interfaces implemented by infra (repositories, gateways) and the base use case
│   ├── entities/           # Models and value objects
│   ├── services/           # Domain services shared by use cases
│   └── usecases/           # One use case per operation
├── infra/                  # Contract implementations: database, HTTP clients, mail, SMS...
├── presentation/
│   ├── factories/          # Build use cases injecting their infra dependencies
│   └── fastapi/            # App config, routes, middlewares and error handlers
└── main/                   # Entry point: loads settings and logging and creates the app
tests/
├── unit/                   # Fast tests with mocked dependencies, mirroring app/
└── integration/            # HTTP tests with TestClient
```

The domain never imports from `infra`, `presentation` or `common`: it declares contracts, `infra` implements them and the factories in `presentation` wire everything together. Domain errors (`NotFoundError`, `ConflictError`...) raised by use cases are turned into HTTP responses by `presentation/fastapi/handlers/domain_error_handler.py`.

### Adding a feature

1. Model in `domain/entities/` and contract in `domain/contracts/`
2. Use case in `domain/usecases/<feature>/`
3. Contract implementation in `infra/`
4. Factory in `presentation/factories/` and route in `presentation/fastapi/routes/` (register it in `routes/__init__.py`)
5. Unit tests in `tests/unit/` and route tests in `tests/integration/`

## AI-assisted development

The template is ready for coding agents such as [Claude Code](https://docs.claude.com/en/docs/claude-code/overview):

- **`CLAUDE.md`** (also `AGENTS.md`, a symlink read by Cursor, Codex and others): architecture rules, commands and the checklist every change must pass before a PR.
- **`.claude/agents/coder.md`**: implements a task on a `claude/<slug>` branch, with tests, runs all checks and opens a PR.
- **`.claude/agents/reviewer.md`**: read-only review of a branch against the project rules.
- **`.claude/settings.json`**: allows the common commands (uv, make, read-only git, gh), denies destructive ones (`rm -rf`, force push, hard reset, reading `.env`) and runs `.claude/hooks/ruff.sh` after every edit, formatting the file and sending unfixable lint errors back to the agent.

Create an empty `.local_dev` file at the root to work directly on your local branch: the agent then edits files without delegating to `coder` or opening PRs.

> [!NOTE]
> The **Personal preferences** section of `CLAUDE.md` holds the template author's own taste (no docstrings, `StrEnum` for fixed strings, latest dependency versions, etc.). They are not part of the architecture — change or remove them to match yours.

## Configuration files

| File                         | Description                                                             |
| ---------------------------- | ----------------------------------------------------------------------- |
| `pyproject.toml`             | Dependencies and ruff, mypy, pytest, coverage, vulture, xenon, import-linter and mutmut config. |
| `uv.lock`                    | Locked dependency versions.                                             |
| `.python-version`            | Python version used by uv.                                              |
| `.pre-commit-config.yaml`    | Git hooks running all quality checks.                                   |
| `scripts/smoke.sh`           | Boot smoke test (`make smoke`).                                         |
| `.github/workflows/mutation.yml` | Weekly / on-demand mutation testing.                                |
| `.env.example`               | Environment variables template.                                         |
| `.github/workflows/ci.yml`   | CI pipeline.                                                            |
| `.github/dependabot.yaml`    | Dependency updates.                                                     |
| `.vscode/settings.json`      | Ruff format on save and pytest integration.                             |
| `CLAUDE.md` / `AGENTS.md`    | Instructions for AI coding agents.                                      |
| `.claude/`                   | Claude Code agents, permissions and hooks.                              |
| `docker/`                    | Dockerfile (`dev` and `production` stages) and docker compose.          |

## License

MIT, see [LICENSE](LICENSE). Free to use, modify and distribute for commercial and non-commercial purposes.

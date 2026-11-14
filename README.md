# py-awesome-template

[![CI](https://github.com/mathmed/py-awesome-template/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/mathmed/py-awesome-template/actions/workflows/ci.yml)
[![Coverage](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/mathmed/py-awesome-template/python-coverage-comment-action-data/endpoint.json)](https://htmlpreview.github.io/?https://github.com/mathmed/py-awesome-template/blob/python-coverage-comment-action-data/htmlcov/index.html)
[![Python 3.14](https://img.shields.io/badge/python-3.14-blue?logo=python&logoColor=white)](https://www.python.org/)
[![Dependabot](https://img.shields.io/badge/dependabot-enabled-025E8C?logo=dependabot)](.github/dependabot.yaml)

A FastAPI template for Python 3.14 with a layered architecture (domain, infra, presentation), managed with [uv](https://docs.astral.sh/uv/), with deterministic quality gates built for AI-written code. Rules, architecture and agent workflow live in [`CLAUDE.md`](CLAUDE.md) (also `AGENTS.md`).

## Getting started

Needs Docker only for `make dev`, and Node.js for `make jscpd` (installs the jscpd pinned in `package-lock.json`).

```sh
make setup   # uv, Python 3.14, dependencies, .env, Node dev tools and git hooks
make run     # API at http://localhost:8000 (docs at /docs); or `make dev` with Docker
make labels  # once per repository: the risk:<level> and deploy:<kind> PR labels (needs gh)
```

```sh
make test            # all tests with coverage (fails under 80%); make test-unit for unit only
make hooks           # every pre-commit check (table below)
make smoke           # boots the real API and calls /health and /ready
make contract        # boots the real API and runs Schemathesis against /openapi.json
make openapi-diff    # breaking OpenAPI changes vs BASE (default origin/main); needs oasdiff
make format-code     # fix lint issues and format with ruff
make build           # production Docker image (dev and production stages in docker/)
```

Add dependencies with `uv add <package>` (`--dev` for tools) and commit `uv.lock`. The full command list is in `CLAUDE.md` and the `Makefile`.

## Environment variables

Read by `app/common/settings.py` from the environment or `.env`; new ones also go in `.env.example`.

| Variable | Default | Description |
| --- | --- | --- |
| `APP_PORT` | - | Host port used by `make dev`. |
| `ENV` | `development` | `development`, `test` or `production` (JSON logs). |
| `LOG_LEVEL` | `INFO` | Python logging level. |
| `CORS_ORIGINS` | `[]` | JSON list of allowed origins, e.g. `["http://localhost:3000"]`. |

## Pipeline

Each check is a CI job (`.github/workflows/ci.yml`) and gates the PR; `scripts/quality_report.py` turns their output into a single **Quality Report** comment per PR (verdict, what to fix with the command to reproduce it, a status table by area).

| Check | Tool | Job | Local |
| --- | --- | --- | --- |
| Lint and format | ruff | `lint` | `make check-code` |
| Types | mypy (strict) | `types` | `make hooks` |
| Code security, vulnerable dependencies | bandit, pip-audit | `security` | `make hooks` |
| Declared dependencies | deptry | `dependencies` | `make deptry` |
| Dead code (advisory) | vulture | `dead-code` | `make hooks` |
| Complexity | xenon | `complexity` | `make hooks` |
| Duplicated code in `app/` (zero clones, `.jscpd.json`) | jscpd | `duplication` | `make jscpd` |
| Suppression ratchet (`suppressions-baseline.json`) | `scripts/suppressions.py` | `suppressions` | `make suppressions` |
| Architecture contracts (`[tool.importlinter]`) | import-linter | `lint-imports` | `make lint-imports` |
| Tests and coverage ≥ 80% | pytest | `tests` | `make test` |
| Boot smoke, `/health` and `/ready` | `scripts/smoke.sh` | `smoke` | `make smoke` |
| API contract | Schemathesis | `contract` | `make contract` |
| Breaking API changes | oasdiff | `openapi-diff` | `make openapi-diff` |
| Mutation testing of the domain (`MUTATION_MIN_SCORE`, default 90) | mutmut | `mutation` | `make mutation-changed` |
| One `risk:*` and one `deploy:*` label | `scripts/pr_labels.py` | `pr-labels` | - |

- **Smoke and contract with real dependencies**: implement `ReadinessCheckContract` in `app/infra/`, register it in `check_readiness_factory`, and set `SMOKE_COMPOSE_FILE`/`SMOKE_MIGRATE_COMMAND` (all options in `scripts/api_server.sh` and `scripts/contract.sh`); in CI add `services:` to both jobs (example in `ci.yml`).
- **oasdiff locally**: `brew install oasdiff` or `go install github.com/oasdiff/oasdiff@latest`; CI pins the version and sha256 in `ci.yml`.
- **Mutation**: `MUTATION_MIN_SCORE` is a repository variable; scope in `[tool.mutmut]`; `make mutation` runs the whole domain (also weekly in `mutation.yml`).

## AI-assisted development

`coder` implements on a branch and leaves handoff notes, `pr-writer` opens the PR with the template and its labels, `reviewer` reviews; only the owner merges (agents in `.claude/agents/`, flow and label rubrics in `CLAUDE.md`). An empty `.local_dev` file at the root makes the agent edit files directly, with no branch or PR. The **Personal preferences** in `CLAUDE.md` are the author's taste: change them freely.

**Porting the PR flow to another language** (e.g. Portuguese): translate only what people read (headings and comments of `.github/pull_request_template.md`, the `Risk:` alert word, the fixed lines `Stacked on #N; merge it first.` and `**Mismatch:**`, the strings quoted in `.claude/agents/pr-writer.md` and in the fallback body of `.claude/agents/coder.md`, the label descriptions in the `Makefile`); keep label names and colors, `scripts/pr_labels.py`, workflow and job names, the `[!WARNING]`/`[!CAUTION]` keywords and Conventional Commits types in English.

## License

MIT, see [LICENSE](LICENSE).

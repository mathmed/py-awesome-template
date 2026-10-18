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
- **CI**: every pull request runs all checks and posts a single **Quality Report** comment with the result of every analysis (see [Quality Report](#quality-report)).
- **Dependabot**: weekly grouped updates for Python dependencies and GitHub Actions.
- **Production basics**: typed settings ([pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)), JSON logs in production, configurable CORS, domain errors mapped to HTTP status codes and `/health` (liveness) and `/ready` (readiness) routes.
- **Deterministic validation for AI-generated code**: a boot smoke test, API contract tests (Schemathesis), breaking-change detection on the OpenAPI schema (oasdiff), architecture contracts, mutation testing, a suppression ratchet and a risk floor that keeps changes to the pipeline itself at high risk (see [Validation layers](#validation-layers)).
- **Docker**: a `dev` stage with hot reload and a slim, non-root `production` stage with healthcheck.
- **AI-ready**: `CLAUDE.md`/`AGENTS.md` with the project rules, Claude Code agents (`coder`, `pr-writer`, `reviewer`), a PR template built for fast review, permissions and a hook that formats every file the agent edits.

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
| `make hooks`       | Run all quality checks (ruff, mypy, bandit, vulture, xenon, import-linter, suppressions, pip-audit). |
| `make smoke`       | Boot the real API and call `/health` and `/ready`.                      |
| `make contract`    | Boot the real API and run Schemathesis against its OpenAPI schema.      |
| `make openapi-diff` | Fail on breaking OpenAPI changes against `BASE` (default `origin/main`). |
| `make risk-floor`  | Print the minimum risk level of the changes against `BASE`.             |
| `make risk-labels` | Create or update the `risk:<level>` labels on GitHub (needs `gh`).      |
| `make lint-imports` | Check the architecture contracts (import-linter).                      |
| `make mutation`    | Mutation testing of the domain (slow); `make mutation-results` lists survivors. |
| `make suppressions` | Fail when the suppressions differ from `suppressions-baseline.json`.   |
| `make suppressions-update` | Lower the suppression baseline after removing suppressions.     |
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

Tests written by an AI agent can pass and still prove little, and an agent under pressure to make a check pass can weaken the check instead of fixing the code. These deterministic layers catch what line coverage does not and make weakening the pipeline visible.

### Boot smoke test (`make smoke`)

`scripts/smoke.sh` boots the API for real (uvicorn, `ENV=production`, environment loaded from `.env.example`), waits for `/health` with a timeout, then calls `/health` (liveness: touches no dependency) and `/ready` (readiness: runs the checks of every real dependency, returns `503` if any is down). On failure it prints the API logs; on exit it always stops everything. It runs in CI as the `smoke` job and blocks the PR.

The template has no database, so `/ready` reports `{"status": "ready", "dependencies": []}`. To adapt it to your project:

1. **Add a dependency check**: implement `ReadinessCheckContract` in `app/infra/` (e.g. a `SELECT 1` on Postgres, catching the driver's specific exceptions and returning `False`) and register it in `app/presentation/factories/check_readiness_factory.py`.
2. **Start the dependencies**: create a compose file with them (e.g. `docker/docker-compose.smoke.yaml` with a Postgres and a `healthcheck`) and run `SMOKE_COMPOSE_FILE=docker/docker-compose.smoke.yaml make smoke`. Make it the default in the script if you want. In CI, use `services:` in the `smoke` job (an example is commented in `ci.yml`).
3. **Run migrations on an empty database**: set `SMOKE_MIGRATE_COMMAND`, e.g. `uv run --no-dev alembic upgrade head`.
4. **Point the app at the dependencies**: put the variables (e.g. `DATABASE_URL`) in `.env.example`; the smoke test boots with exactly that file (`SMOKE_ENV_FILE` picks another one), so no test-only environment hides a broken configuration.

Other options: `SMOKE_PORT` (default `18000`), `SMOKE_TIMEOUT` (default `30` seconds) and `SMOKE_ENV` (default `production`).

The boot itself (environment file, dependencies, migrations, uvicorn, wait for `/health`, cleanup) lives in `scripts/api_server.sh`, which `scripts/smoke.sh` and `scripts/contract.sh` source, so both checks boot the API the same way and accept the same `SMOKE_*` options.

### API contract tests (`make contract`)

`scripts/contract.sh` boots the API like the smoke test and runs [Schemathesis](https://schemathesis.readthedocs.io/) against `/openapi.json` with every check (`--checks all`): no 5xx, documented status codes, content types, headers and response schemas, invalid input rejected and valid input accepted. It generates the requests from the schema FastAPI publishes, so a route that returns something it does not declare, or crashes on an input its signature accepts, fails here even when its unit tests pass.

The pass is bounded and reproducible: one worker, a fixed seed and no example database, so the same code always sends the same requests and a CI failure reproduces locally with `make contract`. Options: `CONTRACT_MAX_EXAMPLES` (test cases per operation and phase, default `50`), `CONTRACT_SEED` (default `1`; change it locally to explore other inputs) and `CONTRACT_REQUEST_TIMEOUT` (seconds per request, default `5`). Extra arguments go to `schemathesis run`, e.g. authentication for protected routes: `./scripts/contract.sh --header "Authorization: Bearer $TOKEN"`. It runs as the `contract` CI job and blocks the PR. On failure the Quality Report shows each failing operation with a `curl` to reproduce it and the API logs.

When it fails, fix the route or declare the response it really returns (`responses=` on the route); do not exclude checks or operations to make it pass.

### Breaking API changes (`make openapi-diff`)

`scripts/openapi.py diff` compares the OpenAPI schema of `HEAD` with the one of the merge base with the base branch and runs [oasdiff](https://github.com/oasdiff/oasdiff) `changelog --fail-on ERR` on them. Removing an endpoint or a response field, making a parameter required or narrowing a type is an error and fails the PR; changes oasdiff classifies as warnings show up as ⚠️, and additive changes are listed for the reviewer in the Quality Report.

Both schemas are generated, nothing is committed: the script imports `app.main.main` and dumps `app.openapi()` for `HEAD`, then checks the merge base out in a temporary `git worktree` and does the same there with that commit's own locked dependencies (`uv run --locked --no-dev`). A committed `openapi.json` would only add a file to keep in sync, and the merge base already is the reference the PR is merged into. Comparing with the merge base instead of the tip of the base branch keeps endpoints added to `main` after the branch was cut from showing up as removals.

It runs as the `openapi-diff` CI job (PRs only, full history). CI downloads a pinned oasdiff release and verifies its sha256 (`OASDIFF_VERSION`/`OASDIFF_SHA256` in `ci.yml`; Dependabot does not track it, bump both together). Locally, install oasdiff (`brew install oasdiff`, `go install github.com/oasdiff/oasdiff@latest` or a [release binary](https://github.com/oasdiff/oasdiff/releases)) and run `make openapi-diff` (`BASE=origin/<branch>` to change the base; `uv run python scripts/openapi.py diff --oasdiff <path>` for a binary outside the `PATH`). To look at the schema itself: `uv run python scripts/openapi.py export --output openapi.json`.

A breaking change is a deliberate product decision, not something to make pass: keep the old route or field, add the new one next to it and deprecate the old one.

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

The scope is `app/domain` (use cases and business rules, `[tool.mutmut]` in `pyproject.toml`); infra, presentation, main and common are covered by integration tests and left out. The `Mutation testing` workflow (called from `ci.yml` on PRs, so its result reaches the Quality Report) runs:

- **on every PR**, mutating only the domain files changed in the diff (`git diff origin/<base>...HEAD` filtered by `source_paths`/`do_not_mutate`). If the PR touches no domain file, the job ends in seconds with "No domain files changed". It fails when the score of the mutated files is below the minimum;
- **weekly** (and on demand via `workflow_dispatch`) on the whole scope, as a safety net.

Reading the run: the **Quality Report** comment has a *Mutation testing* section with the score, the threshold, killed/survived counts and the survivors (file and function). The job's **Summary** tab has the same data in more detail. It shows the score, killed vs survived counts and a table of the survivors with file, function and mutant name. Run `uv run mutmut show <mutant>` locally to see the diff.

**Tuning.** The gate is the repository variable `MUTATION_MIN_SCORE` (Settings → Secrets and variables → Actions → Variables; default `90`, locally it is read from the environment). Set it to your project's baseline. The scope is `[tool.mutmut]` in `pyproject.toml` (`source_paths`, `do_not_mutate`); the PR job follows it automatically. Only changes to files in scope trigger mutation; test-only changes do not.

`mutants/` is mutmut's working copy (copies of the code plus per-mutant results). It is regenerated on every run, is large and machine specific, and mutmut reuses stored results for unchanged source files even when the tests changed, so a stale copy can hide survivors: keep it out of git (it is in `.gitignore`) and delete it if results look stale. CI caches it with an exact key over domain code, tests and lockfile.

Reading the result:

```sh
make mutation           # whole domain, then prints the score and the survivors
make mutation-changed   # only domain files changed vs origin/main (BASE=... to change), as the PR job does
make mutation-results   # lists the survivors
uv run mutmut show <name>   # diff of a surviving mutant: what changed and no test noticed
```

Score per module = killed ÷ total mutants. For each survivor, either add the missing assertion, or, if the mutant does not change behaviour (an equivalent mutant), leave it. Don't lower the scope to raise the score.

### Suppression ratchet (`make suppressions`)

`scripts/suppressions.py` counts, per file and per kind, every suppression in `app/`, `scripts/` and `tests/`:

| Kind | Matches |
| --- | --- |
| `noqa` | `# noqa`, `# noqa: E501`, `# ruff: noqa` |
| `type-ignore` | `# type: ignore`, `# type: ignore[code]` |
| `nosec` | `# nosec` (bandit) |
| `no-cover` | `# pragma: no cover`, `# pragma: no branch` |
| `pylint-disable` / `mypy-directive` / `pyright-directive` | `# pylint: disable=...`, `# mypy: ...`, `# pyright: ...` |
| `formatter-off` | `# fmt: off`, `# fmt: skip`, `# isort: skip_file`... |
| `test-skip` / `test-xfail` | `pytest.mark.skip`/`skipif`/`xfail`, `pytest.skip()`/`importorskip()`/`xfail()`, `unittest.skip*`/`expectedFailure`, `self.skipTest()` |

Comments are read with `tokenize` and tests with `ast`, so the same text inside a string does not count. The counts are compared with the committed `suppressions-baseline.json`:

- **a count went up** (a new suppression, or one moved to another file): the check fails and lists the file, kind and lines. Remove the suppression and fix the cause. Raising the baseline (`uv run python scripts/suppressions.py update --allow-increase`) needs the owner's explicit approval, and the baseline change shows up in the PR diff;
- **a count went down**: the check also fails until you run `make suppressions-update` and commit the lower baseline in the same PR, so the improvement is locked in and reviewed;
- **counts match**: the check passes.

It runs as a pre-commit hook, in `make hooks` and as the `suppressions` CI job. Configuration that disables checks globally (`pyproject.toml`, `.pre-commit-config.yaml`, the workflows) is not counted here: changing any of those files puts the PR at the `high` risk floor (see [Risk floors and the risk label](#risk-floors-and-the-risk-label)), and the `pr-writer` agent always lists pipeline changes under **Look here**.

### Risk floors and the risk label

Every PR carries exactly one `risk:low`, `risk:medium`, `risk:high` or `risk:critical` label, assigned by the `pr-writer` agent when it opens the PR (see [Pull request flow](#pull-request-flow)). Some files set a minimum: `.github/risk-floors.yaml` lists, per category, the globs that put a PR at least at that level. It starts with three categories, all `high`:

| Category | Paths |
| --- | --- |
| pipeline config | `pyproject.toml`, `.pre-commit-config.yaml`, `Makefile`, `suppressions-baseline.json`, `scripts/**`, `.github/**`, `.claude/**`, `CLAUDE.md`, `AGENTS.md` |
| migrations | `**/migrations/**`, `**/alembic/**`, `alembic.ini` |
| auth | `**/*auth*`, `**/*permission*` (files and directories) |

`make risk-floor` prints the floor of the current branch and the files behind it; the `pr-writer` agent runs the same command, so the agent and CI agree. The **Risk label** workflow (`.github/workflows/risk-label.yml`) runs `scripts/risk.py check` on every push and every label change and fails when the PR has no risk label, more than one, an unknown one, or one below the floor. It is a separate workflow so that changing a label does not re-run the whole CI, and for that reason it is not part of the Quality Report. The second floor rule (any deploy step other than "None" is at least `medium`) depends on the PR description, so only the agent applies it.

The floor is what keeps a change to the pipeline from passing as a minor one: such a PR is always labeled at least `high` and its pipeline changes are listed under **Look here**. It does not require a specific reviewer's approval; merging stays with the owner.

Create the labels once with `make risk-labels` (idempotent: `gh label create --force`). Dependabot PRs get `risk:high` through `labels` in `.github/dependabot.yaml`, since they touch `pyproject.toml` or the workflows. To add a category, append an entry with `category`, `level` and `paths` to the YAML file; the check picks it up on the next run.

## Quality Report

Every pull request gets **one** comment (marker `<!-- quality-report -->`, updated in place on every push) with the verdict, a status table and a section per analysis: ✅ ok, ⚠️ warning, ❌ failed, ⏭️ not run (job cancelled/skipped, or nothing to do, e.g. no domain file changed for mutation testing). Long output goes inside collapsible `<details>`.

| Section | Tool | Job | What the section shows |
| --- | --- | --- | --- |
| Lint/format | ruff check + format | `lint` | problem / file count; output on failure |
| Types | mypy (strict) | `types` | files checked or error count |
| Security | bandit + pip-audit | `security` | issues and vulnerable dependencies |
| Dead code | vulture | `dead-code` | items found (⚠️, advisory: does not block) |
| Complexity | xenon | `complexity` | blocks above the threshold |
| Suppressions | `scripts/suppressions.py` | `suppressions` | total vs. baseline; new or removed suppressions by file, kind and line |
| Tests and coverage | pytest + coverage | `tests` | passed/failed/total, coverage vs. minimum |
| Architecture | import-linter | `lint-imports` | contracts kept/broken; broken contract and violating import |
| Boot smoke | `scripts/smoke.sh` | `smoke` | booted?, `/health` and `/ready`, time to healthy; API logs only on failure |
| API contract | Schemathesis (`scripts/contract.sh`) | `contract` | test cases, operations and seed; on failure the failing checks, a `curl` per failure and the API logs |
| Breaking API changes | oasdiff (`scripts/openapi.py`) | `openapi-diff` | breaking changes (❌), possible breaking changes (⚠️) and every API change with its endpoint |
| Mutation testing | mutmut (`mutation.yml`) | `mutation` | score vs. threshold, killed/survivors, survivors by file/function |

**How it works.** Each analysis job runs its tool through `scripts/quality_report.py run <analysis> -- <command>`. The wrapper streams the output, returns the tool's own exit code (the job is still the gate; the report never decides what blocks) and saves a *fragment* `quality-fragments/<analysis>.json`, which the job uploads as the `quality-fragment-<job>` artifact. The final `quality-report` job (`needs` every analysis, `if: always()`, only on PRs, `pull-requests: write`) downloads the fragments, runs `scripts/quality_report.py render` and upserts the comment. A job that failed, was cancelled or produced no fragment appears as ❌ / ⏭️ instead of breaking the report. The report is also written to the job summary, which is the fallback for PRs from forks, where the token is read-only and posting the comment only emits a warning (this fork path is not validated by the PR that introduced it).

Coverage is part of the report: the separate coverage comment no longer exists on PRs, and `python-coverage-comment-action` only updates the README badge on push to `main`.

**Fragment contract.** A fragment is a JSON file `{"analysis": "<id>", "exit_code": 0, "output": "<tool output>", "advisory": false}`. The renderer parses `output` with one function per analysis, so the format of each section is tested in `tests/unit/scripts/test_quality_report.py`. `advisory` (`--advisory` in the wrapper) records the real exit code but makes the wrapper exit 0, for checks that only inform (vulture). Mutation testing also prints a `MUTATION_RESULT: {json}` line (see `scripts/mutation.py`) and the suppression ratchet a `SUPPRESSIONS_RESULT: {json}` line (see `scripts/suppressions.py`).

**Adding an analysis.**

1. Add a value to `Analysis` and an `analyze_<tool>(fragment) -> Finding` function (status, one-line summary, optional details) in `scripts/quality_report.py`, register it in `ANALYZERS` and add a `Section` (title, job name, analyses) to `SECTIONS` in the order you want.
2. Create the job in `ci.yml` running the tool as `uv run --locked python scripts/quality_report.py run <analysis> -- <command>`, then upload `quality-fragments/` as the artifact `quality-fragment-<job>` with `if: ${{ !cancelled() }}`.
3. Add the job to the `needs` of `quality-report`.
4. Add tests with a sample of the tool's output.

Render locally from fragments: `uv run python scripts/quality_report.py render --dir quality-fragments`.

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
- **`.claude/agents/coder.md`**: implements a task on a `claude/<slug>` branch, with tests, runs all checks, commits, pushes and leaves handoff notes. It opens the PR itself only as a fallback.
- **`.claude/agents/pr-writer.md`**: reads the pushed branch cold, commit by commit, fills the PR template, assigns the risk level, opens the PR with its `risk:<level>` label and stops. Never writes code, never merges.
- **`.claude/agents/reviewer.md`**: read-only review of a branch against the project rules.
- **`.claude/settings.json`**: allows the common commands (uv, make, read-only git, gh), denies destructive ones (`rm -rf`, force push, hard reset, reading `.env`) and runs `.claude/hooks/ruff.sh` after every edit, formatting the file and sending unfixable lint errors back to the agent.

Create an empty `.local_dev` file at the root to work directly on your local branch: the agent then edits files without delegating to `coder` or opening PRs.

### Pull request flow

Reading AI-written diffs is the bottleneck, so the PR description tells the reviewer how much attention the PR deserves and what changed in behavior and in rules, written by an agent that did not write the code:

1. **`coder`** implements on a branch, runs every check, commits one logical step per commit, pushes and writes **handoff notes** to `.handoff/<branch>.md` (gitignored): the task verbatim, what was done and why, decisions, deploy notes and an explicit **Not verified** list. It does not open the PR or assess the risk.
2. **`pr-writer`** (Opus) gets the task, the branch and the notes. It reads the diff commit by commit, writes behavior items per commit and aggregates them, and fills `.github/pull_request_template.md`:
   - **Risk**: `low | medium | high | critical` with one line of why. It assigns the level itself, never below `make risk-floor` (pipeline config, migrations and auth are `high`), and at least `medium` when there are deploy steps;
   - **Summary**: one sentence on what changes in behavior and why;
   - **Behavior**: at most five *before → after* items about rules and observable behavior, never "file X changed", each with a clickable permalink to the test or function that proves it, or "none found";
   - **Unchanged**, **Look here** (what deserves human eyes), **Deploy steps** (always present; "None: normal merge and deploy." when nothing is needed) and an honest **Not verified**, plus a **Mismatch** line when the diff contradicts the handoff notes.

   It opens the PR with the `risk:<level>` label (creating the labels if missing) and stops.
3. **Fallback**: if `pr-writer` fails, `coder` opens the PR with a minimal body (summary plus the template headings, risk "unassessed", no label), so a failure never blocks delivery; the [Risk label](#risk-floors-and-the-risk-label) check stays red until a person sets the label.
4. **Merge**: only the owner merges. The Quality Report comment and the Risk label check run on every PR.

People opening PRs by hand get the same template from GitHub.

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
| `scripts/contract.sh`        | Schemathesis contract test (`make contract`).                           |
| `scripts/api_server.sh`      | API boot shared by the smoke and contract tests.                        |
| `scripts/openapi.py`         | OpenAPI export and breaking-change diff against the base branch (`make openapi-diff`). |
| `.github/workflows/mutation.yml` | Mutation testing on PRs (changed files), weekly and on demand.      |
| `scripts/mutation.py`        | Mutation target selection, summary and score gate.                      |
| `scripts/quality_report.py`  | Runs analyses as CI fragments and renders the single Quality Report.    |
| `scripts/suppressions.py`    | Suppression ratchet (`make suppressions`).                              |
| `suppressions-baseline.json` | Committed suppression counts per file and kind.                         |
| `.github/risk-floors.yaml`   | Minimum risk level per file category, read by `scripts/risk.py` and the `pr-writer` agent. |
| `scripts/risk.py`            | Risk floor of a diff and the risk label check (`make risk-floor`).      |
| `.github/workflows/risk-label.yml` | Fails PRs without a single risk label at or above the floor.      |
| `.env.example`               | Environment variables template.                                         |
| `.github/workflows/ci.yml`   | CI pipeline: one job per analysis plus the `quality-report` job.        |
| `.github/dependabot.yaml`    | Dependency updates.                                                     |
| `.github/pull_request_template.md` | PR description structure: risk, behavior, look here, deploy steps. |
| `.vscode/settings.json`      | Ruff format on save and pytest integration.                             |
| `CLAUDE.md` / `AGENTS.md`    | Instructions for AI coding agents.                                      |
| `.claude/`                   | Claude Code agents, permissions and hooks.                              |
| `docker/`                    | Dockerfile (`dev` and `production` stages) and docker compose.          |

## License

MIT, see [LICENSE](LICENSE). Free to use, modify and distribute for commercial and non-commercial purposes.

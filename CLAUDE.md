# CLAUDE.md

Guidance for AI coding agents working in this repository. `AGENTS.md` is a symlink to this file, so
Cursor, Codex and other tools that read `AGENTS.md` follow the same rules.

## Project

FastAPI API template on Python 3.14, managed with [uv](https://docs.astral.sh/uv/). See the README for
setup, environment variables and the folder structure.

## Commands

```bash
make setup        # install uv, dependencies and git hooks
make run          # run the API locally with hot reload
make test         # all tests with coverage (fails under 80%)
make test-unit    # only the fast unit tests
make hooks        # all quality checks: ruff, mypy, bandit, vulture, xenon, import-linter, suppressions,
                  # conventions, pip-audit
make smoke        # boots the real API and calls /health and /ready
make contract     # boots the real API and runs Schemathesis against its OpenAPI schema
make openapi-diff # fails on breaking OpenAPI changes vs BASE (default origin/main); needs oasdiff
make risk-labels  # create/update the risk:<level> labels on GitHub
make lint-imports # architecture contracts (import-linter)
make mutation     # mutation testing of the whole domain (slow; weekly in CI)
make mutation-changed # mutation testing of only the domain files changed vs BASE (default origin/main); runs on every PR
make suppressions # suppression ratchet: fails when noqa/type: ignore/nosec/skip/ruff per-file-ignores...
                  # differ from the baseline
make suppressions-update # lower suppressions-baseline.json after removing suppressions (never raises it)
make conventions  # the code preferences no linter checks: fails on any violation, with no baseline
make format-code  # fix lint issues and format with ruff
```

Always use `uv run` / `uv add` — never `pip` directly.

## Architecture rules

```
app/common/        settings and logging, importable by any layer
app/domain/        business core: contracts, entities, usecases, services, errors, enums, constants
app/infra/         implementations of domain contracts (database, HTTP clients, mail...)
app/presentation/  factories (dependency wiring) and FastAPI (routes, middlewares, handlers)
app/main/          entry point
tests/fakes/       helpers shared by the test suites (fakes, builders)
tests/unit/        fast tests with mocked dependencies, mirroring app/
tests/integration/ HTTP tests with TestClient
```

- `app/domain` never imports from `app/infra`, `app/presentation` or `app/common`. It declares contracts
  (ABCs in `domain/contracts/`); `infra` implements them; `presentation/factories` wires them together.
- Use cases extend `Usecase[Params, Response]`, have one public method (`execute`) and receive their
  dependencies through the constructor.
- Business failures raise the errors from `app/domain/errors/` (`NotFoundError`, `ConflictError`...).
  Never raise `HTTPException` outside `presentation`; the domain error handler maps them to HTTP status.
- New routes go in `presentation/fastapi/routes/` and must be registered in `routes/__init__.py`.
- New environment variables go in `app/common/settings.py` (with a default when possible), in
  `.env.example` and in the README environment variables table.
- CI analyses never post comments on their own: each job runs its tool through
  `scripts/quality_report.py run <analysis> -- <command>` and uploads the fragment; the `quality-report` job
  builds the single PR comment. A new analysis needs an `Analysis` value, an analyzer, a `Section`, a job
  uploading `quality-fragment-<job>`, an entry in the `needs` of `quality-report` and tests (see the README,
  "Quality Report"). The wrapper keeps the tool's exit code: the job stays the gate.
- Every change comes with tests: unit tests for use cases and infra (mock external dependencies) and
  integration tests for routes.

## Before opening a PR (mandatory)

1. The app imports: `uv run python -c "import app.main.main"`.
2. New environment variables have a default or an entry in `.env.example`.
3. `make hooks` (which runs `suppressions` and `conventions`), `make test`, `make lint-imports`,
   `make smoke` and `make contract` pass, and so does `make openapi-diff` when `oasdiff` is installed (CI
   always runs it). A PR with failing checks is not a PR.
4. Existing routes are not removed or renamed unless the task asks for it.
5. The README is updated if the change affects setup, commands, routes, env vars or architecture.

## Deterministic validation

- `make lint-imports` enforces the architecture rules above as import-linter contracts in
  `pyproject.toml` (`[tool.importlinter]`). If it fails, fix the import, not the contract. Never relax,
  remove or add an `ignore_imports` to a contract without the user's explicit approval.
- `make smoke` boots the API for real and calls `/health` (liveness, touches no dependency) and `/ready`
  (readiness, touches the real dependencies). A new infra dependency needs a `ReadinessCheckContract`
  implementation registered in `check_readiness_factory`.
- `make suppressions` is a ratchet whose goal is zero: it compares every `# noqa`, `# type: ignore`,
  `# nosec`, `# pragma: no cover`, `# pragma: no mutate`, tool directive (`# pylint:`, `# mypy:`,
  `# pyright:`, `# fmt: off`), skipped/xfail test (`collect_ignore` included) in `app/`, `scripts/` and
  `tests/` and every code under `[tool.ruff.lint.per-file-ignores]` with `suppressions-baseline.json`,
  and fails when a `ruff.toml` or `.ruff.toml` exists, which ruff would read instead of `pyproject.toml`.
  Fix the cause instead of suppressing it. Never raise the baseline (`update --allow-increase`) without
  the user's explicit approval. When you remove suppressions, run `make suppressions-update` and commit
  the lower baseline in the same PR.
- `make conventions` (`scripts/conventions.py`) fails on any violation of the preferences marked
  (conventions) below, listing file, line and kind. There is no baseline and no exception: fix the code.
  It reads every directory with versioned Python (a test fails when one is left out). Changing a marked
  preference means changing the check in the same PR.
- Pipeline and agent files (`pyproject.toml`, `.pre-commit-config.yaml`, `Makefile`, `scripts/`, `.github/`,
  `.claude/`, `CLAUDE.md`, `suppressions-baseline.json`): do not change them unless the task asks for it,
  and call the change out in the PR.
- `make contract` boots the API like `make smoke` and runs a bounded Schemathesis pass (fixed seed) against
  `/openapi.json`: responses must match the documented status codes and schemas, invalid input must be
  rejected and nothing may return a 5xx. Fix the route or document the response (`responses=` in the
  route), never exclude the check or the operation.
- `make openapi-diff` exports the OpenAPI schema of HEAD and of the merge base with the base branch and runs
  `oasdiff changelog --fail-on ERR`: removing or renaming a route, a response field or making a parameter
  required fails the PR. Public contracts only grow additively; a deliberate breaking change needs the
  user's explicit approval and is called out in the PR.
- Mutation testing runs on every PR (`Mutation testing` workflow, only the domain files changed in the diff)
  and weekly on the whole domain. The job fails when the score of the mutated scope is below
  `MUTATION_MIN_SCORE` (repository variable, default 90). Surviving mutants are listed in the run summary
  with file and function: add the missing assertion, do not weaken or delete tests or shrink the scope.
  Never commit `mutants/` (mutmut's working copy, in `.gitignore`).

## Critical surfaces

> Template placeholder: every repository derived from this template replaces the examples below with its
> own list, written after reading its code. Name the modules, routes or jobs, not generic categories.

The parts of the system where a failure is hardest to undo. The `pr-writer` agent reads this list before
labelling a PR `risk:high` or `risk:critical`; a change that touches none of them rarely is either.

- **Authentication and permissions**: who can sign in and what each caller is allowed to do.
- **Money or irreversible data movement**: charges, payouts, transfers, deletions, messages sent to people.
- **The only recovery path**: backups, rollback and migration tooling, the deploy pipeline, anything a
  person needs to undo a bad change.

## Workflow

1. **Implement**: code changes are delegated to the `coder` agent (`.claude/agents/coder.md`), which creates
   a branch, implements, reviews its own diff against every directive, commits (one commit per logical
   step), pushes and writes the handoff notes. It does not open the PR and does not assess the risk. Never
   commit directly to `main`.
2. **Review** (mandatory): then delegate to the `reviewer` agent (`.claude/agents/reviewer.md`) with the
   branch, the base branch and the path of the handoff notes. It only reads and returns its report, grouped
   by severity with a verdict; whoever orchestrates saves the report verbatim to
   `.handoff/<branch>.review.md`.
3. **Fix**: give `coder` the path of the whole report. It fixes the blocking findings, pushes and records
   under Decisions, with the reason, each non-blocking finding it leaves out.
4. **Describe and open**: then delegate to the `pr-writer` agent (`.claude/agents/pr-writer.md`) with the
   original task verbatim, the branch, the base branch, the path of the handoff notes and the path of the
   review report. It reads the diff cold, commit by commit, fills `.github/pull_request_template.md` (with
   the Review section), assigns the risk level by the rubric in that file (most PRs low or medium; high or
   critical only with one concrete sentence naming what can break; at least medium when there are deploy
   steps), opens the PR with the `risk:<level>` label and stops. It never writes code. Behavior items are
   plain language with no file, function, test or code references; the evidence pointers for them go only
   in **Look here**, and a behavior without evidence is listed under **Not verified**.
5. **Fallbacks**: if `reviewer` fails or cannot run, go on to `pr-writer`, which writes **No review.**
   prominently in the PR. If `pr-writer` fails or cannot run, delegate back to `coder` saying so: it opens
   the PR itself with a minimal body (summary plus the template headings, risk "unassessed", no risk
   label), so a failure never blocks delivery. The Risk label check stays red until a person sets the
   label.
6. **Merge**: nobody but the owner merges. Agents never merge, approve or enable auto-merge.

- **Exception**: if a `.local_dev` file exists at the repository root, the developer is working locally —
  edit files directly, without delegating to the agents and without creating commits or PRs.
- The `reviewer` agent also reviews, on request, a branch or PR that did not go through this flow.

### Handoff notes

The `coder` writes them to `.handoff/<branch>.md` (every `/` of the branch name replaced with `-`; the
directory is gitignored) after pushing, next to the reviewer's report (`.handoff/<branch>.review.md`).
`reviewer` and `pr-writer` check them against the diff, and `pr-writer` reports a **Mismatch** when they
disagree. Sections, in this order:

- `## Task`: the original task, verbatim.
- `## Done`: what changed and why, one line per item.
- `## Decisions`: choices made, alternatives rejected, conservative options taken on non-blocking doubts,
  review findings left out and why.
- `## Deploy notes`: new env vars or secrets, migrations and their order, flags, external configuration; or
  "None".
- `## Not verified`: everything the author did not or could not check, and why; or "nothing".

## Personal preferences

> These are the personal preferences of the template author. They are not requirements of the
> architecture: change, remove or replace them with your own. Everything above this section describes how
> the template works; everything below is taste.

`(conventions)` and `(ruff)` mark what `make conventions` and ruff enforce, with `partly` when they cover
only part of the preference. Nothing checks the rest: check it by hand. When you change or remove a marked
preference, change the check too (`scripts/conventions.py` or `[tool.ruff.lint]` in `pyproject.toml`).

- **New standards**: whenever the user asks to change a code pattern (use enums instead of strings, name
  variables a certain way...), ask whether it should become a project standard. If yes, add it to this
  list so it is followed in every future conversation.
- **Reuse first (YAGNI)**: follow the existing pattern, where it complies with this file, instead of
  inventing one. Before creating a function, class, module, contract, service or dependency, check whether
  one already exists and reuse it. When you change shared code, find and update every caller.
- **Single responsibility**: each module/class has one reason to change. If a module needs to import from
  two unrelated integrations, extract the dependency to an intermediary.
- **SOLID beyond SRP**: open for extension, closed for modification; depend on abstractions (domain
  contracts) received through the constructor. Injected dependencies are mandatory — no
  `repo: Repo | None = None` with a hidden fallback.
- **DDD**: invariants, calculations and state transitions live as methods of the entity or value object,
  with no I/O or external dependencies. Request/response DTOs only carry data and validation. Value
  objects are immutable (`@dataclass(frozen=True)`).
- **Data access**: only through a contract implemented in `infra`. It only persists and fetches — no
  business rules there and no ad-hoc queries anywhere else.
- **`__init__.py`**: only create one when it actually exports symbols. Never create empty `__init__.py`
  files just to mark packages.
- **File order** (conventions, partly): constants and classes at the top, then functions; public before
  private, inside a class too (the check only reads the module body).
- **Comments and docstrings** (conventions): no docstrings on modules, functions, methods or classes. A
  comment only records what the code cannot say, and every prose comment starts with the mark of its case:
  `Constraint:` (an external constraint nobody would guess from the code, such as a vendor API limit or a
  database column type that drops the time zone), `Pitfall:` (a trap already paid for, with the concrete
  case) or `Tradeoff:` (a choice between plausible alternatives, saying why the other one fails). An
  unmarked comment is a violation, and the reviewer checks that the mark is honest. Never comment what the
  code does.
- **Identifiers** (conventions, partly): every identifier (variables, functions, classes, parameters,
  fields) in English. Booleans start with `is_`, `has_`, `should_` or `can_`, local variables included
  (the check reads functions, parameters and fields).
- **Language**: all code, comments, logs, docs and user-facing text (including CI reports) in English.
- **Class names** (conventions): never prefix class names with `_`.
- **Typing**: every parameter and return value is typed, and `Any` is not used unless there is no
  alternative (and the reason is written next to it). Use `X | None` and built-in generics, never
  `Optional`/`Union`; `# type: ignore` only with the error code.
- **Data structures**: always use `BaseModel` or `dataclass` for structured data. Use `dict` only as a last
  resort.
- **Enums**: always use `enum.StrEnum` for fixed sets of strings (status, types, roles...). Never spread
  hardcoded strings across the code.
- **No magic values** (conventions, partly): limits, timeouts, truncations and URLs are named constants
  at the top of the module (`_UPPER` when private) or in `app/domain/constants/`. Constant collections are
  `tuple`/`frozenset` or an immutable `Mapping` (the check reads module constants).
- **Money and exact values**: always `Decimal`, never `float`.
- **Dates** (ruff): always timezone-aware UTC — `datetime.now(UTC)`. Never `datetime.now()` or
  `datetime.utcnow()`.
- **Edge cases**: before implementing, list the states, dates and input values that can reach the code and
  handle each one. Irreversible effects (charge, send, delete) happen exactly once.
- **Idempotency**: repeating the same call (retry, webhook redelivery, double click) never duplicates an
  effect — use an idempotency key, an upsert or a state check.
- **Fail loudly** (ruff, partly): never swallow exceptions (no `except Exception: pass`). Catch specific
  exceptions only where something can be done; log unexpected errors with `logger.exception` and propagate
  or translate them. Only best-effort side effects may continue, after logging.
- **Nothing internal leaks**: error messages are written for people — no exception text, vendor or
  infrastructure names or internal ids in responses.
- **Hot paths**: no N+1 (query or call inside a loop) and no slow work on paths every request goes through.
- **Functions** (conventions and ruff, partly): small (a function up to 50 lines, a class up to 250 lines
  and 20 public methods, a module up to 400 lines); a short orchestrator composes verb-named helpers.
  Booleans and many optional parameters are keyword-only (`*`). Imports are absolute and at the top; local
  imports only to break a cycle.
- **Early return**: prefer guard clauses and early returns over nested `if`s.
- **Thin routes**: a route only converts the request, calls the use case and returns the response. No
  business rules in `presentation`.
- **Use case names**: start with a verb (`CreateUser`, `ListInvoices`), one use case per file.
- **Public API**: every new endpoint is authenticated unless explicitly declared public, and validates its
  input at the edge. Public contracts only grow additively — never remove or rename a route or response
  field.
- **Security**: never put tokens, passwords, secrets or personal data in logs, exception messages or the
  repository. Compare secrets with `hmac.compare_digest`, load YAML with `yaml.safe_load`, and call
  `subprocess` with an argument list, a `timeout` and no `shell=True`.
- **Logging** (ruff, partly): never use `print` (outside `scripts/`, whose output is the product); always
  `logger = logging.getLogger(__name__)`.
- **Configuration**: read settings only from `app/common/settings.py`; never `os.getenv` elsewhere.
- **Dependencies**: always use the latest available version of any external library.
- **README**: after any relevant change (new route, command, setup step, env var or architecture change),
  check whether the README needs updating and update it.
- **Tests** (conventions, partly): name them `test_should_<behaviour>` and build the object under test in
  a `sut` fixture.
- **Commits**: Conventional Commits in English — `<type>: <short description>`, with `feat`, `fix`,
  `refactor`, `chore`, `test`, `docs`, `ci` or `build`.

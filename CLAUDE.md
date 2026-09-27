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
make hooks        # all quality checks: ruff, mypy, bandit, vulture, xenon, pip-audit
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
- Every change comes with tests: unit tests for use cases and infra (mock external dependencies) and
  integration tests for routes.

## Before opening a PR (mandatory)

1. The app imports: `uv run python -c "import app.main.main"`.
2. New environment variables have a default or an entry in `.env.example`.
3. `make hooks` and `make test` pass. A PR with failing checks is not a PR.
4. Existing routes are not removed or renamed unless the task asks for it.
5. The README is updated if the change affects setup, commands, routes, env vars or architecture.

## Workflow

- Code changes are delegated to the `coder` agent (`.claude/agents/coder.md`), which creates a branch,
  implements, commits and opens a PR. Never commit directly to `main`.
- **Exception**: if a `.local_dev` file exists at the repository root, the developer is working locally —
  edit files directly, without delegating to `coder` and without creating commits or PRs.
- Use the `reviewer` agent (`.claude/agents/reviewer.md`) to review a branch against these rules before
  merging.

## Personal preferences

> These are the personal preferences of the template author. They are not requirements of the
> architecture: change, remove or replace them with your own. Everything above this section describes how
> the template works; everything below is taste.

- **New standards**: whenever the user asks to change a code pattern (use enums instead of strings, name
  variables a certain way...), ask whether it should become a project standard. If yes, add it to this
  list so it is followed in every future conversation.
- **`__init__.py`**: only create one when it actually exports symbols. Never create empty `__init__.py`
  files just to mark packages.
- **Comments and docstrings**: no docstrings on functions, methods or classes. Comments only when the code
  is genuinely confusing and the reason is not obvious from the names. Never comment what the code does.
- **Enums**: always use `enum.StrEnum` for fixed sets of strings (status, types, roles...). Never spread
  hardcoded strings across the code.
- **Data structures**: always use `BaseModel` or `dataclass` for structured data. Use `dict` only as a last
  resort.
- **Identifiers**: every identifier (variables, functions, classes, parameters, fields) in English.
- **Class names**: never prefix class names with `_`.
- **Single responsibility**: each module/class has one reason to change. If a module needs to import from
  two unrelated integrations, extract the dependency to an intermediary.
- **Dependencies**: always use the latest available version of any external library.
- **README**: after any relevant change (new route, command, setup step, env var or architecture change),
  check whether the README needs updating and update it.
- **Typing**: every parameter and return value is typed, and `Any` is not used unless there is no
  alternative (and the reason is written next to it). mypy runs in strict mode.
- **Logging**: never use `print`; always `logger = logging.getLogger(__name__)`. Never log tokens,
  passwords, secrets or personal data.
- **Dates**: always timezone-aware UTC — `datetime.now(UTC)`. Never `datetime.now()` or `datetime.utcnow()`.
- **Thin routes**: a route only converts the request, calls the use case and returns the response. No
  business rules in `presentation`.
- **Use case names**: start with a verb (`CreateUser`, `ListInvoices`), one use case per file.
- **Exceptions**: never `except Exception: pass`. Catch specific exceptions, and only where something
  can be done about them.
- **Early return**: prefer guard clauses and early returns over nested `if`s.
- **Tests**: name them `test_should_<behaviour>` and build the object under test in a `sut` fixture.
- **Commits**: Conventional Commits in English — `<type>: <short description>`, with `feat`, `fix`,
  `refactor`, `chore`, `test`, `docs`, `ci` or `build`.

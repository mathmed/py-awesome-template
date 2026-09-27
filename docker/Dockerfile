FROM python:3.14-slim AS base

COPY --from=ghcr.io/astral-sh/uv:0.12 /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

# Development: the project is mounted as a volume and started with --reload (see docker-compose.yaml)
FROM base AS dev

# Keep the container venv outside the mounted project folder so it doesn't clash with the host .venv
ENV UV_PROJECT_ENVIRONMENT=/opt/venv

WORKDIR /home/app

COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod 755 /usr/local/bin/entrypoint.sh

EXPOSE 8000

ENTRYPOINT [ "entrypoint.sh" ]

# Build: install only production dependencies
FROM base AS builder

ENV UV_COMPILE_BYTECODE=1

WORKDIR /app

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-dev --no-install-project

COPY app ./app

# Production: slim runtime with a non-root user
FROM python:3.14-slim AS production

ENV PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    ENV=production

RUN useradd --create-home --uid 1000 app

COPY --from=builder --chown=app:app /app /app

USER app
WORKDIR /app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

CMD [ "uvicorn", "app.main.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log" ]

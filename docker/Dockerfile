FROM python:3.14-slim

WORKDIR /

RUN mkdir /home/app

COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh

RUN chmod 755 /usr/local/bin/entrypoint.sh && ln -s /usr/local/bin/entrypoint.sh

# To control project dependencies
COPY --from=ghcr.io/astral-sh/uv:0.12 /uv /uvx /bin/

# Keep the container venv outside the mounted project folder so it doesn't clash with the host .venv
ENV UV_PROJECT_ENVIRONMENT=/opt/venv

EXPOSE 80

ENTRYPOINT [ "entrypoint.sh" ]

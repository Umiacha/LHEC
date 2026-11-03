FROM python:3.12.14-slim-trixie

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends gettext \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

COPY pyproject.toml uv.lock ./

RUN uv sync --locked --no-dev

COPY . .

RUN DJANGO_SECRET_KEY=build-only-secret \
    DJANGO_DEBUG=False \
    DATABASE_URL=postgresql://build:build@localhost/build \
    uv run python manage.py compilemessages --ignore=.venv \
    && DJANGO_SECRET_KEY=build-only-secret DJANGO_DEBUG=False \
    DATABASE_URL=postgresql://build:build@localhost/build \
    uv run python manage.py collectstatic --noinput

RUN useradd --create-home appuser

COPY entrypoint.sh /app/entrypoint.sh

ENV DJANGO_DEBUG=False

USER appuser

CMD ["sh", "/app/entrypoint.sh"]

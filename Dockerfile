FROM python:3.12.14-slim-trixie

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

COPY pyproject.toml uv.lock ./

RUN uv sync --locked --no-dev

COPY . .

RUN DJANGO_SECRET_KEY=build-only-secret \
    DJANGO_DEBUG=False \
    uv run python manage.py collectstatic --noinput

RUN useradd --create-home appuser
USER appuser

CMD ["uv", "run", "gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000"]
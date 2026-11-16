FROM python:3.14-slim

ENV PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN pip install "poetry==1.8.3" \
    && poetry config virtualenvs.create false

COPY pyproject.toml poetry.lock ./
RUN poetry install --only main --no-root --no-interaction --no-ansi

COPY bot_factories/managed_bots/admin ./bot_factories/managed_bots/admin
COPY bot_factories/managed_bots/shared ./bot_factories/managed_bots/shared

CMD ["python", "-m", "bot_factories.managed_bots.admin.json_worker"]

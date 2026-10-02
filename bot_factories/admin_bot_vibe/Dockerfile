FROM python:3.14-slim

ENV PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN pip install "poetry==1.8.3" \
    && poetry config virtualenvs.create false

COPY pyproject.toml poetry.lock ./
RUN poetry install --only main --no-root --no-interaction --no-ansi

COPY bot_factories/admin_bot ./bot_factories/admin_bot
COPY shared ./shared
COPY worker ./worker

CMD ["celery", "-A", "bot_factories.admin_bot.celery_app", "worker", "--loglevel=info", "--concurrency=1", "--pool=solo"]

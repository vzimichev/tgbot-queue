FROM python:3.14-slim

ENV PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
RUN pip install "poetry==1.8.3" \
    && poetry config virtualenvs.create false
COPY pyproject.toml poetry.lock ./
RUN poetry install --only main --no-root --no-interaction --no-ansi
COPY api ./api
COPY bot_factories ./bot_factories
COPY shared ./shared
COPY worker ./worker

EXPOSE 8000
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM python:3.13-slim

WORKDIR /app

COPY pyproject.toml poetry.lock* /app/
RUN pip install --upgrade pip \
    && pip install poetry \
    && poetry config virtualenvs.create false \
    && poetry install --no-dev

COPY . /app

CMD ["celery", "-A", "worker.celery_app.celery_app", "worker", "--loglevel=info"]

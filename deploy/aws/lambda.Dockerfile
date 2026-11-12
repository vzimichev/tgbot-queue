# syntax=docker/dockerfile:1
# Pass an image digest through LAMBDA_BUILD_IMAGE for repeatable releases.
ARG LAMBDA_BUILD_IMAGE=public.ecr.aws/lambda/python:3.13
FROM ${LAMBDA_BUILD_IMAGE} AS build

# Kombu's SQS transport includes pycurl, which needs native build tools.
RUN dnf install -y gcc libcurl-devel && dnf clean all
RUN python -m venv /opt/build-tools \
    && /opt/build-tools/bin/pip install --no-cache-dir poetry==1.8.3

WORKDIR /build
ENV POETRY_VIRTUALENVS_IN_PROJECT=true POETRY_NO_INTERACTION=1
COPY pyproject.toml poetry.lock ./
RUN /opt/build-tools/bin/poetry install --only main --no-root --no-ansi

# Explicit allowlist: never copy .env files, SQLite databases or test fixtures.
COPY shared/config.py shared/managed_webhook.py /asset/shared/
COPY worker/celery_app.py worker/celery_factory.py worker/celery_tasks.py /asset/worker/
COPY bot_factories/__init__.py /asset/bot_factories/
COPY bot_factories/admin_bot/__init__.py bot_factories/admin_bot/lambda_webhook.py /asset/bot_factories/admin_bot/
RUN cp -a /build/.venv/lib/python3.13/site-packages/. /asset/

# Smoke-test native imports in the actual Lambda OS before publishing.
RUN cd /asset && CELERY_BROKER=sqs SQS_REGION=eu-central-1 \
    SQS_QUEUE_URL=https://sqs.eu-central-1.amazonaws.com/000000000000/build-check \
    python -c 'import sys; sys.path.insert(0, "."); import pycurl; from bot_factories.admin_bot.lambda_webhook import handler; assert callable(handler)'
COPY deploy/aws/package_lambda.py /build/package_lambda.py
RUN python /build/package_lambda.py /asset /output/lambda-webhook.zip

FROM scratch AS artifact
COPY --from=build /output/lambda-webhook.zip /

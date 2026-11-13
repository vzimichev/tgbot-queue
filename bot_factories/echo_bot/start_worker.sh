#!/usr/bin/env bash

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$PROJECT_DIR"

ENV_FILE="${1:-$PROJECT_DIR/bot_factories/echo_bot/.env}"
if [[ "$ENV_FILE" != /* ]]; then
    ENV_FILE="$PROJECT_DIR/$ENV_FILE"
fi
if [[ ! -f "$ENV_FILE" ]]; then
    echo "Error: $ENV_FILE not found. Copy bot_factories/echo_bot/.env.example and fill in credentials." >&2
    exit 1
fi

set -a
# shellcheck disable=SC1091
source "$ENV_FILE"
set +a
export APP_ENV_FILE="$ENV_FILE"

: "${TELEGRAM_TOKEN:?TELEGRAM_TOKEN is not set in the echo env file}"

if [[ ! -x .venv/bin/celery ]]; then
    if ! command -v poetry >/dev/null 2>&1; then
        echo "Error: Poetry is not installed and .venv/bin/celery is missing." >&2
        exit 1
    fi

    echo "Installing project dependencies..."
    poetry install --no-interaction
fi

echo "Starting echo worker. Press Ctrl+C to stop."
.venv/bin/celery \
    -A bot_factories.echo_bot.celery_app \
    worker \
    --loglevel=info \
    --concurrency=1 \
    --pool=solo

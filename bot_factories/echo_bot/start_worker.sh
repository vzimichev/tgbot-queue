#!/usr/bin/env bash

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TUNNEL_PID=""

cleanup() {
    if [[ -n "$TUNNEL_PID" ]] && kill -0 "$TUNNEL_PID" 2>/dev/null; then
        echo "Stopping SSH tunnel..."
        kill "$TUNNEL_PID"
        wait "$TUNNEL_PID" 2>/dev/null || true
    fi
}

trap cleanup EXIT INT TERM

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

: "${SSH_HOST:?SSH_HOST is not set in the echo env file}"
: "${SSH_REDIS_PORT:?SSH_REDIS_PORT is not set in the echo env file}"
: "${REDIS_HOST:?REDIS_HOST is not set in the echo env file}"
: "${REDIS_PORT:?REDIS_PORT is not set in the echo env file}"
: "${REDIS_PASSWORD:?REDIS_PASSWORD is not set in the echo env file}"
: "${TELEGRAM_TOKEN:?TELEGRAM_TOKEN is not set in the echo env file}"

if [[ ! -x .venv/bin/celery ]]; then
    if ! command -v poetry >/dev/null 2>&1; then
        echo "Error: Poetry is not installed and .venv/bin/celery is missing." >&2
        exit 1
    fi

    echo "Installing project dependencies..."
    poetry install --no-interaction
fi

echo "Opening Redis tunnel through $SSH_HOST..."
ssh \
    -N \
    -o BatchMode=yes \
    -o ExitOnForwardFailure=yes \
    -o ServerAliveInterval=30 \
    -o ServerAliveCountMax=3 \
    -L "${REDIS_HOST}:${REDIS_PORT}:127.0.0.1:${SSH_REDIS_PORT}" \
    "$SSH_HOST" &
TUNNEL_PID=$!

sleep 1
if ! kill -0 "$TUNNEL_PID" 2>/dev/null; then
    wait "$TUNNEL_PID" || true
    echo "Error: SSH tunnel could not be opened." >&2
    exit 1
fi

echo "Starting echo worker. Press Ctrl+C to stop."
.venv/bin/celery \
    -A bot_factories.echo_bot.celery_app \
    worker \
    --loglevel=info \
    --concurrency=1 \
    --pool=solo

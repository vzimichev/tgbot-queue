#!/usr/bin/env bash

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="${1:-$PROJECT_DIR/bot_factories/admin_bot/.env}"
TUNNEL_PID=""

cleanup() {
    if [[ -n "$TUNNEL_PID" ]] && kill -0 "$TUNNEL_PID" 2>/dev/null; then
        kill "$TUNNEL_PID"
        wait "$TUNNEL_PID" 2>/dev/null || true
    fi
}
trap cleanup EXIT INT TERM

if [[ ! -f "$ENV_FILE" ]]; then
    echo "Error: $ENV_FILE not found." >&2
    exit 1
fi

cd "$PROJECT_DIR"
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a
export APP_ENV_FILE="$ENV_FILE"

: "${SSH_HOST:?SSH_HOST is not set}"
: "${SSH_REDIS_PORT:?SSH_REDIS_PORT is not set}"
: "${REDIS_HOST:?REDIS_HOST is not set}"
: "${REDIS_PORT:?REDIS_PORT is not set}"
: "${REDIS_PASSWORD:?REDIS_PASSWORD is not set}"
: "${ADMIN_BOT_FACESWAP_API_BASE_URL:?ADMIN_BOT_FACESWAP_API_BASE_URL is not set}"

ssh -N -o BatchMode=yes -o ExitOnForwardFailure=yes \
    -o ServerAliveInterval=30 -o ServerAliveCountMax=3 \
    -L "${REDIS_HOST}:${REDIS_PORT}:127.0.0.1:${SSH_REDIS_PORT}" "$SSH_HOST" &
TUNNEL_PID=$!

sleep 1
if ! kill -0 "$TUNNEL_PID" 2>/dev/null; then
    wait "$TUNNEL_PID" || true
    echo "Error: Redis tunnel could not be opened." >&2
    exit 1
fi

.venv/bin/celery -A bot_factories.admin_bot.celery_app worker \
    --loglevel=info --concurrency=1 --pool=solo -Q faceswap_jobs

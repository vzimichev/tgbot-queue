#!/usr/bin/env bash

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TUNNEL_PID=""
API_PID=""
WORKER_PID=""

cleanup() {
    for pid in "$WORKER_PID" "$API_PID" "$TUNNEL_PID"; do
        if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
            kill "$pid"
            wait "$pid" 2>/dev/null || true
        fi
    done
}

trap cleanup EXIT INT TERM
cd "$PROJECT_DIR"

if [[ ! -f .env ]]; then
    echo "Error: $PROJECT_DIR/.env not found." >&2
    exit 1
fi

set -a
# shellcheck disable=SC1091
source .env
set +a

: "${SSH_HOST:?SSH_HOST is not set in .env}"
: "${SSH_REDIS_PORT:?SSH_REDIS_PORT is not set in .env}"
: "${REDIS_HOST:?REDIS_HOST is not set in .env}"
: "${REDIS_PORT:?REDIS_PORT is not set in .env}"
: "${FACESWAP_CLIENT_DIR:?FACESWAP_CLIENT_DIR is not set in .env}"
: "${FACESWAP_API_HOST:?FACESWAP_API_HOST is not set in .env}"
: "${FACESWAP_API_PORT:?FACESWAP_API_PORT is not set in .env}"

if [[ ! -x .venv/bin/celery ]]; then
    echo "Installing bot dependencies..."
    poetry install --no-interaction
fi

if [[ ! -x "$FACESWAP_CLIENT_DIR/.venv/bin/uvicorn" ]]; then
    echo "Error: FaceFusion environment not found in $FACESWAP_CLIENT_DIR/.venv" >&2
    exit 1
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
    echo "Error: SSH tunnel could not be opened. Is another worker running?" >&2
    exit 1
fi

echo "Starting FaceFusion API on ${FACESWAP_API_HOST}:${FACESWAP_API_PORT}..."
(
    cd "$FACESWAP_CLIENT_DIR"
    export PYTHONPATH="$FACESWAP_CLIENT_DIR/facefusion${PYTHONPATH:+:$PYTHONPATH}"
    exec .venv/bin/uvicorn app:app --host "$FACESWAP_API_HOST" --port "$FACESWAP_API_PORT"
) &
API_PID=$!

for _ in {1..30}; do
    if curl -fsS "http://${FACESWAP_API_HOST}:${FACESWAP_API_PORT}/health" >/dev/null 2>&1; then
        break
    fi
    if ! kill -0 "$API_PID" 2>/dev/null; then
        wait "$API_PID" || true
        echo "Error: FaceFusion API stopped during startup." >&2
        exit 1
    fi
    sleep 1
done

if ! curl -fsS "http://${FACESWAP_API_HOST}:${FACESWAP_API_PORT}/health" >/dev/null; then
    echo "Error: FaceFusion API did not become ready." >&2
    exit 1
fi

echo "Starting face-swap worker. Press Ctrl+C to stop."
.venv/bin/celery \
    -A bot_factories.faceswap_bot.celery_app \
    worker \
    --loglevel=info \
    --concurrency=1 \
    --pool=solo &
WORKER_PID=$!

# If the tunnel, API, or worker exits, stop the whole stack instead of leaving
# Celery retrying forever against a dead local port. This loop is compatible
# with the Bash 3.2 version bundled with macOS (which has no `wait -n`).
while kill -0 "$TUNNEL_PID" 2>/dev/null \
    && kill -0 "$API_PID" 2>/dev/null \
    && kill -0 "$WORKER_PID" 2>/dev/null; do
    sleep 1
done

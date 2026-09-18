#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$PROJECT_DIR"

if [[ ! -f .env ]]; then
    echo "Error: $PROJECT_DIR/.env not found." >&2
    exit 1
fi

# Python reads .env as data; do not execute its contents as shell commands.
echo "Starting admin bot (polling + SQLite). Press Ctrl+C to stop."
if [[ -x .venv/bin/python ]]; then
    exec .venv/bin/python -m bot_factories.admin_bot.polling
elif command -v poetry >/dev/null 2>&1; then
    exec poetry run python -m bot_factories.admin_bot.polling
else
    echo "Error: install dependencies with poetry install first." >&2
    exit 1
fi

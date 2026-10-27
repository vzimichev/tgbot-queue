#!/bin/sh

set -u

payload=$(cat)
case "$payload" in
  *".py"*|*"pyproject.toml"*|*"poetry.lock"*) ;;
  *) exit 0 ;;
esac

root=$(git rev-parse --show-toplevel) || exit 1
cd "$root" || exit 1

status=0

if [ -x .venv/bin/black ]; then
  .venv/bin/black --check api worker shared bot_factories || status=1
elif command -v poetry >/dev/null 2>&1; then
  poetry run black --check api worker shared bot_factories || status=1
else
  echo "Lint skipped: Black is not installed." >&2
  status=1
fi

if [ -x .venv/bin/ruff ]; then
  .venv/bin/ruff check api worker shared bot_factories || status=1
elif command -v poetry >/dev/null 2>&1; then
  poetry run ruff check api worker shared bot_factories || status=1
else
  echo "Lint skipped: Ruff is not installed." >&2
  status=1
fi

exit "$status"

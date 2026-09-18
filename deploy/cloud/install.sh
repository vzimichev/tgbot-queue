#!/usr/bin/env bash
# Install the cloud gateway on Debian 13 or Ubuntu 26.04 with HTTPS in Nginx.
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SERVICE_NAME="tgbot-gateway"
UNIT_PATH="/etc/systemd/system/${SERVICE_NAME}.service"

die() { echo "Error: $*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || die "run with sudo or as root"
[[ -f "$PROJECT_DIR/.env" ]] || die "$PROJECT_DIR/.env is missing"
if command -v python3.14 >/dev/null; then
    PYTHON_BIN=python3.14
elif command -v python3.13 >/dev/null; then
    PYTHON_BIN=python3.13
else
    die "Python 3.13 or 3.14 is required"
fi
for command_name in poetry redis-cli nginx systemctl curl useradd; do
    command -v "$command_name" >/dev/null || die "$command_name is required"
done

# Read .env as data. Never source a credentials file into a root shell.
mapfile -t config < <("$PYTHON_BIN" - "$PROJECT_DIR/.env" <<'PY'
import sys
from pathlib import Path

values = {}
for line in Path(sys.argv[1]).read_text().splitlines():
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    key, value = line.split("=", 1)
    values[key.strip()] = value.strip().strip("\"'")
for key in ("REDIS_HOST", "REDIS_PORT", "REDIS_PASSWORD",
            "WEBHOOK_SECRET_TOKEN", "TELEGRAM_TASK_NAME", "TELEGRAM_QUEUE"):
    if not values.get(key):
        raise SystemExit(f"Error: {key} must be set in .env")
if values["REDIS_HOST"] not in ("127.0.0.1", "localhost"):
    raise SystemExit("Error: REDIS_HOST must point to local Redis on the cloud host")
if not values["REDIS_PORT"].isdigit():
    raise SystemExit("Error: REDIS_PORT must be numeric")
print(values["REDIS_HOST"])
print(values["REDIS_PORT"])
print(values["REDIS_PASSWORD"])
PY
)
[[ ${#config[@]} -eq 3 ]] || die "invalid .env"
REDIS_HOST="${config[0]}"
REDIS_PORT="${config[1]}"
nginx -t
systemctl enable --now redis-server nginx
REDISCLI_AUTH="${config[2]}" redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" ping | grep -qx PONG \
    || die "Redis is unavailable or REDIS_PASSWORD is incorrect"

cd "$PROJECT_DIR"
# A separate Poetry project avoids reusing an older .venv that may run other workers.
BUILD_DIR="$PROJECT_DIR/.cloud-build"
mkdir -p "$BUILD_DIR"
cp pyproject.toml poetry.lock "$BUILD_DIR/"
export POETRY_VIRTUALENVS_IN_PROJECT=false
export POETRY_VIRTUALENVS_PATH="$PROJECT_DIR/.venvs-cloud"
cd "$BUILD_DIR"
poetry env use "$PYTHON_BIN"
poetry install --only main --no-root --no-interaction
VENV_DIR="$(poetry env info --path)"
[[ -x "$VENV_DIR/bin/uvicorn" ]] || die "uvicorn was not installed"

# Run the gateway with its own account. The application also reads .env itself.
if ! id -u tgbot-gateway >/dev/null 2>&1; then
    useradd --system --no-create-home --shell /usr/sbin/nologin tgbot-gateway
fi
chown tgbot-gateway:tgbot-gateway "$PROJECT_DIR/.env"
chmod 600 "$PROJECT_DIR/.env"
sed -e "s|@PROJECT_DIR@|$PROJECT_DIR|g" \
    -e "s|@VENV_DIR@|$VENV_DIR|g" \
    "$PROJECT_DIR/deploy/cloud/tgbot-gateway.service.in" > "$UNIT_PATH"
chmod 644 "$UNIT_PATH"
systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
systemctl restart "$SERVICE_NAME"
ready=false
for _ in {1..10}; do
    if curl --fail --silent --max-time 2 http://127.0.0.1:8000/openapi.json >/dev/null; then
        ready=true
        break
    fi
    sleep 1
done
[[ $ready == true ]] || die "gateway did not answer on 127.0.0.1:8000; check journalctl -u $SERVICE_NAME"
echo "Gateway is running. Redis and Nginx remain under their existing systemd services."

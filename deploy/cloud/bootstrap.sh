#!/usr/bin/env bash
# Provision a fresh Ubuntu 26.04 or Debian 13 gateway host.
# Usage: sudo bash bootstrap.sh DOMAIN /root/gateway.env [CERTBOT_EMAIL]
set -euo pipefail

REPO_URL="https://github.com/vzimichev/tgbot-queue.git"
REPO_BRANCH="codex/admin-bot-cloud"
PROJECT_DIR="/opt/tgbot-queue"
DOMAIN="${1:-}"
ENV_SOURCE="${2:-}"
CERTBOT_EMAIL="${3:-}"

die() { echo "Error: $*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || die "run as root or with sudo"
[[ $DOMAIN =~ ^[a-z0-9]([a-z0-9.-]*[a-z0-9])?$ && $DOMAIN == *.* ]] \
    || die "pass a valid DNS domain as the first argument"
[[ -f $ENV_SOURCE ]] || die "pass an existing gateway .env file as the second argument"
[[ -z $CERTBOT_EMAIL || $CERTBOT_EMAIL == *@*.* ]] \
    || die "the optional certificate email is invalid"

# A small Droplet can run out of RAM during package installation.
if [[ $(awk '/MemTotal:/ {print $2}' /proc/meminfo) -lt 1048576 ]] \
    && ! swapon --show --noheadings | grep -q .; then
    if [[ ! -f /swapfile ]]; then
        fallocate -l 1G /swapfile
        chmod 600 /swapfile
        mkswap /swapfile >/dev/null
    fi
    swapon /swapfile
    grep -q '^/swapfile ' /etc/fstab \
        || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq \
    git python3-poetry python3-venv redis-server nginx \
    certbot python3-certbot-nginx curl
command -v python3.13 >/dev/null || command -v python3.14 >/dev/null \
    || die "the OS must provide Python 3.13 or 3.14"

if [[ ! -d $PROJECT_DIR/.git ]]; then
    git clone --branch "$REPO_BRANCH" --single-branch "$REPO_URL" "$PROJECT_DIR"
else
    [[ -z $(git -C "$PROJECT_DIR" status --porcelain) ]] \
        || die "repository has local changes; refusing to overwrite them"
    git -C "$PROJECT_DIR" fetch origin "$REPO_BRANCH"
    git -C "$PROJECT_DIR" checkout "$REPO_BRANCH"
    git -C "$PROJECT_DIR" merge --ff-only FETCH_HEAD
fi

if [[ $ENV_SOURCE != "$PROJECT_DIR/.env" ]]; then
    install -m 600 "$ENV_SOURCE" "$PROJECT_DIR/.env"
fi
chmod 600 "$PROJECT_DIR/.env"

# Parse credentials as data and never print them or source them into a shell.
python3 - "$PROJECT_DIR/.env" <<'PY'
import re
import sys
from pathlib import Path

values = {}
for line in Path(sys.argv[1]).read_text().splitlines():
    line = line.strip()
    if not line or line.startswith('#') or '=' not in line:
        continue
    key, value = line.split('=', 1)
    values[key.strip()] = value.strip().strip("\"'")
for key in ('REDIS_HOST', 'REDIS_PORT', 'REDIS_PASSWORD',
            'WEBHOOK_SECRET_TOKEN', 'TELEGRAM_TASK_NAME', 'TELEGRAM_QUEUE',
            'ADMIN_BOT_TOKEN', 'ADMIN_BOT_OWNER_ID',
            'ADMIN_BOT_PUBLIC_BASE_URL', 'ADMIN_BOT_WEBHOOK_SECRET'):
    if not values.get(key):
        raise SystemExit(f'Error: {key} is missing from .env')
if not values['ADMIN_BOT_OWNER_ID'].isdigit() or int(values['ADMIN_BOT_OWNER_ID']) <= 0:
    raise SystemExit('Error: ADMIN_BOT_OWNER_ID must be a positive integer')
if values['REDIS_HOST'] not in ('127.0.0.1', 'localhost'):
    raise SystemExit('Error: REDIS_HOST must be local')
if values['REDIS_PORT'] != '6379':
    raise SystemExit('Error: the bootstrap configures Redis on port 6379')
password = values['REDIS_PASSWORD']
if not re.fullmatch(r'[A-Za-z0-9_.~!@#$%^&*+=:-]+', password):
    raise SystemExit('Error: REDIS_PASSWORD contains unsupported config characters')
path = Path('/etc/redis/redis.conf')
lines = path.read_text().splitlines()
settings = {'bind': '127.0.0.1', 'protected-mode': 'yes',
            'requirepass': password}
kept = [line for line in lines
        if not any(re.match(rf'^\s*{key}\s+', line) for key in settings)]
path.write_text('\n'.join(kept + [f'{key} {value}' for key, value in settings.items()]) + '\n')
PY
systemctl enable --now redis-server
systemctl restart redis-server
systemctl enable --now nginx

# Certbot retains its generated HTTPS configuration on subsequent runs.
if [[ ! -f /etc/letsencrypt/live/$DOMAIN/fullchain.pem ]]; then
    python3 - "$DOMAIN" <<'PY'
import sys
from pathlib import Path

domain = sys.argv[1]
site = Path('/etc/nginx/sites-available/tgbot-gateway')
site.write_text(f'''server {{
    listen 80;
    server_name {domain};
    location / {{
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }}
}}
''')
link = Path('/etc/nginx/sites-enabled/tgbot-gateway')
if not link.exists():
    link.symlink_to(site)
Path('/etc/nginx/sites-enabled/default').unlink(missing_ok=True)
PY
    nginx -t
    systemctl reload nginx
    certbot_args=(--nginx --non-interactive --agree-tos --redirect -d "$DOMAIN")
    if [[ -n $CERTBOT_EMAIL ]]; then
        certbot_args+=(--email "$CERTBOT_EMAIL")
    else
        certbot_args+=(--register-unsafely-without-email)
    fi
    certbot "${certbot_args[@]}"
fi

bash "$PROJECT_DIR/deploy/cloud/install.sh"

curl --fail --silent --show-error --max-time 15 \
    "https://$DOMAIN/openapi.json" >/dev/null
echo "Cloud gateway is ready at https://$DOMAIN/webhook"

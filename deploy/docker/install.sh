#!/usr/bin/env bash
set -euo pipefail

DOMAIN="${1:?Usage: install.sh domain}"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
if [[ "$EUID" -ne 0 ]]; then
    echo "Run as root." >&2
    exit 1
fi
if [[ ! "$DOMAIN" =~ ^[a-zA-Z0-9][a-zA-Z0-9.-]*[a-zA-Z0-9]$ ]]; then
    echo "Invalid domain." >&2
    exit 1
fi
if [[ ! -f "$PROJECT_DIR/.env" ]]; then
    echo "Missing $PROJECT_DIR/.env" >&2
    exit 1
fi

# A 512 MB VM needs swap while Docker builds and starts Python.
if [[ "$(awk '/MemTotal:/ {print $2}' /proc/meminfo)" -lt 1048576 ]] \
    && [[ "$(swapon --noheadings --show | wc -l)" -eq 0 ]]; then
    fallocate -l 1G /swapfile
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    if ! grep -q '^/swapfile ' /etc/fstab; then
        printf '/swapfile none swap sw 0 0\n' >> /etc/fstab
    fi
fi

apt-get update
apt-get install -y docker.io docker-compose-v2 certbot
systemctl enable --now docker

cd "$PROJECT_DIR"
mkdir -p deploy/docker/certbot-webroot
if [[ -f "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" ]]; then
    sed "s/\${DOMAIN}/$DOMAIN/g" \
        deploy/docker/nginx.https.conf.template > deploy/docker/nginx.active.conf
else
    cp deploy/docker/nginx.http.conf deploy/docker/nginx.active.conf
fi
docker compose up -d --build

if [[ ! -f "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" ]]; then
    certbot certonly --webroot \
        --webroot-path "$PROJECT_DIR/deploy/docker/certbot-webroot" \
        --non-interactive --agree-tos --register-unsafely-without-email \
        -d "$DOMAIN"
fi

sed "s/\${DOMAIN}/$DOMAIN/g" \
    deploy/docker/nginx.https.conf.template > deploy/docker/nginx.active.conf
docker compose exec -T nginx nginx -t
docker compose exec -T nginx nginx -s reload

cat > /etc/letsencrypt/renewal-hooks/deploy/tgbot-nginx <<EOF
#!/usr/bin/env bash
cd "$PROJECT_DIR"
docker compose exec -T nginx nginx -s reload
EOF
chmod 755 /etc/letsencrypt/renewal-hooks/deploy/tgbot-nginx
systemctl enable --now certbot.timer

docker compose ps

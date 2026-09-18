#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."
.venv/bin/python -c 'from bot_factories.admin_bot.config import admin_settings; admin_settings.validate_runtime()'
exec .venv/bin/celery -A bot_factories.admin_bot.celery_app worker --loglevel=info --concurrency=1 --pool=solo -Q admin_bot -n 'admin@%h'

# Telegram Processing Gateway

A lightweight **FastAPI + Celery** gateway for building Telegram bots that rely on **heavy local processing**—AI image/video generation, audio transcription, face-swapping, large ML models, or any CPU/GPU-intensive tasks.

## Why this project exists

Telegram bots deployed to the cloud cannot efficiently run heavy AI pipelines.

This project solves the problem with a hybrid approach:

- Deploy only a **lightweight webhook gateway** to any cheap cloud VM.

- Run the **heavy workers locally** (or anywhere with GPUs/CPUs).

This lets you prototype AI-powered bots **locally**, with full GPU access, while keeping cloud costs minimal.

## Features
### Core Functionality

- **Webhook Gateway** (FastAPI) — receives Telegram updates securely.

- **Queue** (Redis) — decouples your cloud and local machines.

- **Workers** (Celery) — execute heavy processing (AI/ML/audio/video/etc.).

- **Bot** (Aiogram) — write simple Aiogram handlers; everything else is handled automatically.

### Architecture Benefits

- Local/Remote Hybrid: run GPU tasks locally, gateway in the cloud.

- Fully Modular: gateway, worker, and bot logic are isolated.

- Easy Experimentation: ideal for prototyping creative AI bot ideas.

- Production-Friendly: keep heavy tasks off your cloud instance.

## Folder Structure

    /api                 – FastAPI webhook  
    /worker              – Celery setup  
    /bot_factories       – isolated aiogram bot implementations
    /shared              – configs, clients  

If you want to build a fully customized bot, place it inside
`bot_factories`.\
Bot customization is essentially about defining **aiogram routes and
handlers**.\
The rest of the architecture remains unchanged.

### Architecture Overview:

    Telegram → FastAPI → Celery Task → Redis → Worker → Aiogram Bot → Telegram API

Aiogram **does not receive webhooks directly** --- it runs inside a
Celery worker.

## Requirements

- Python 3.13 or 3.14
- Docker (only for the Docker deployment)
- Telegram Bot Token
- Domain name (Telegram requires HTTPS for webhooks)

## Configuration

Create `.env` in project root:

``` env
TELEGRAM_TOKEN=123456:ABC
WEBHOOK_SECRET_TOKEN=super-secret

REDIS_HOST=redis
REDIS_PORT=6379
REDIS_PASSWORD=guest1

# Select the task and queue belonging to the worker this gateway serves.
TELEGRAM_TASK_NAME=echo_bot.process_telegram_update
TELEGRAM_QUEUE=echo_bot
TELEGRAM_REQUEST_TIMEOUT=600
```

All variables are loaded via `shared/config.py`.

## Running the Cloud Gateway

### Without Docker (Debian 13 or Ubuntu)

On a fresh Ubuntu 26.04 or Debian 13 server, point your domain at the server
and allow inbound TCP ports 80 and 443. Create a private `/root/gateway.env`:

```env
WEBHOOK_SECRET_TOKEN=replace-with-a-random-secret
REDIS_HOST=127.0.0.1
REDIS_PORT=6379
REDIS_PASSWORD=replace-with-a-random-password
TELEGRAM_TASK_NAME=faceswap_bot.process_telegram_update
TELEGRAM_QUEUE=faceswap_bot
```

Use a password made of letters, digits and common punctuation without spaces.
Download and run the bootstrap script, passing your real domain and env file:

```sh
curl -fsSLo bootstrap.sh https://raw.githubusercontent.com/vzimichev/tgbot-queue/codex/cloud-gateway-deploy/deploy/cloud/bootstrap.sh
sudo bash bootstrap.sh tgbot-queue.duckdns.org /root/gateway.env
```

The bootstrap adds swap on small machines, installs packages, checks out this
branch in `/opt/tgbot-queue`, configures local-only Redis, runs
`deploy/cloud/install.sh`, and configures Nginx and a Let's Encrypt certificate.
It can be rerun to update the checkout. Pass an email address as a third
argument if you want certificate expiry notices. The bot token stays on the
worker machine; configure the Telegram webhook separately after bootstrap.
No Celery worker is started on the cloud host.

The script uses Python 3.14 on Ubuntu 26.04 and Python 3.13 on Debian 13.
The lock file includes wheels for both. Ubuntu 24.04 has Python 3.12 by default.

### With Docker

Start all cloud-side services:
``` bash
docker compose up -d --build
```

This starts:

- **gateway**: FastAPI server receiving Telegram webhook calls
- **redis**: Message broker
- **flower**: Celery monitoring UI

View logs:

``` bash
docker compose logs -f
```

Stop and remove containers + volumes:

``` bash
docker compose down -v
```

## Running the Worker

Run your local worker that contains the **aiogram bot handlers** and executes heavy processing:

``` bash
bot_factories/echo_bot/start_worker.sh
```
This lets you run AI-heavy tasks (audio/video processing, image generation, etc.) locally, while the cloud instance only receives webhooks.

## Setting the Telegram Webhook

After the cloud gateway is online, point your bot to it:

``` bash
curl -X POST "https://api.telegram.org/bot<token>/setWebhook" \
  -d "url=https://your_domain/webhook" \
  -d "secret_token=<WEBHOOK_SECRET_TOKEN>"
```

Webhook endpoint:
```
https://your-domain.com/webhook
```

## Custom Bots

To create a custom bot:

1. Add a package inside `bot_factories/`.
2. Keep its routes, service configuration, launch scripts, and specific tests in that package.
3. Create a Celery app with a unique task name and queue name.
4. Configure the gateway's `TELEGRAM_TASK_NAME` and `TELEGRAM_QUEUE` to match.

The shared gateway and worker modules contain no service-specific processing code.

The FaceSwap integration test is opt-in because it requires a running local
FaceFusion HTTP service and ignored media fixtures under
`bot_factories/faceswap_bot/tests/data/`:

``` bash
RUN_FACESWAP_INTEGRATION=1 .venv/bin/pytest bot_factories/faceswap_bot/tests/test_integration.py
```

## License

MIT

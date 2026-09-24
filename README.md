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

The project root `.env` contains gateway credentials only. Start from
`.env.example`:

``` env
WEBHOOK_SECRET_TOKEN=super-secret

REDIS_HOST=redis
REDIS_PORT=6379
REDIS_PASSWORD=guest1

# Select the task and queue belonging to the worker this gateway serves.
```

All variables are loaded via `shared/config.py`.

Local bot credentials belong in separate, ignored files:

| File | Used by |
| --- | --- |
| `bot_factories/echo_bot/.env` (or one file per echo bot) | Echo Celery worker and its SSH tunnel |
| `bot_factories/faceswap_bot/.env` | FaceSwap worker, SSH tunnel, and local FaceFusion API |
| `bot_factories/admin_bot/.env` | Admin Celery worker and its SSH tunnel |

Copy the matching `.env.example` file in each bot directory and fill in its
credentials. Each launcher loads its own file. To run two echo bots, copy
`bot_factories/echo_bot/.env.example` to `bot_factories/echo_bot/.env.echo1` and
`bot_factories/echo_bot/.env.echo2`. Give them separate Telegram tokens and
local Redis ports. Each bot must use its own Redis broker so its worker only
consumes that bot's updates. FaceSwap uses local port 6380 by default. Start the workers in separate
terminals:

```bash
./bot_factories/echo_bot/start_worker.sh bot_factories/echo_bot/.env.echo1
./bot_factories/echo_bot/start_worker.sh bot_factories/echo_bot/.env.echo2
./bot_factories/faceswap_bot/start_worker.sh
./bot_factories/admin_bot/start_worker.sh
```

Each bot needs its own gateway deployment, Redis broker, and webhook. The
gateway publishes `telegram.process_update` to `telegram_updates`.
The Compose file runs one gateway deployment.

### Admin bot factory

Copy `bot_factories/admin_bot/.env.example` to `bot_factories/admin_bot/.env`,
set `ADMIN_BOT_TOKEN`, your numeric `ADMIN_BOT_OWNER_ID`, and the SSH/Redis
settings for its gateway. Enable Bot Management Mode for the admin bot in
BotFather. Set the admin bot's webhook to that gateway's `/webhook` endpoint
with `allowed_updates=["message", "managed_bot"]`. The gateway publishes the
usual `telegram.process_update` task to `telegram_updates`; the admin worker
consumes it through its SSH tunnel. Give the admin bot a separate Redis broker
from other bots because they use the same task name and queue.

The admin worker and its persistent SQLite database can also run in their own
Docker Compose project while using the root gateway and Redis. See
[`bot_factories/admin_bot/README.md`](bot_factories/admin_bot/README.md) for the
startup instructions.

Run `./bot_factories/admin_bot/start_worker.sh` for the local worker setup. In
the admin bot's private chat, the **Создать бота / добавить лимит** button asks you to choose a Telegram user and enter a limit in seconds.
Confirm managed bot creation yourself with the offered button and keep its
suggested username. You remain its owner. The admin bot saves the token and
limit and creates a one-time link to the personal bot. When the recipient opens
that link, the worker reads their real Telegram ID, restricts the bot to that
account, and consumes the link. If the user
already has a saved bot, selecting them shows the existing invitation (or the
ordinary bot link after activation). For a pending creation, it shows the
creation button again. **Добавить лимит** separately starts budget input. **Мои боты** lists saved bots and invitations. Parameters and managed bot tokens are stored in
`bot_factories/admin_bot/.cache/admin.sqlite3`.
The generated bots have no handlers yet; the limit is stored but is not spent.

## Running the Cloud Gateway

### Without Docker (Debian 13 or Ubuntu)

On a fresh Ubuntu 26.04 or Debian 13 server, point your domain at the server
and allow inbound TCP ports 80 and 443. Create a private `/root/gateway.env`:

```env
WEBHOOK_SECRET_TOKEN=replace-with-a-random-secret
REDIS_HOST=127.0.0.1
REDIS_PORT=6379
REDIS_PASSWORD=replace-with-a-random-password
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

On a fresh Ubuntu server, copy the project to `/opt/tgbot-queue` and create a
private `.env` there with `WEBHOOK_SECRET_TOKEN`, `REDIS_PASSWORD`,
`REDIS_HOST=redis`, and `REDIS_PORT=6379`. Point the domain at the server, then run:

```bash
sudo bash deploy/docker/install.sh your-domain.example
```

The installer adds swap on small VMs, installs Docker and Certbot, starts the
FastAPI gateway, Redis, and Nginx, and obtains a Let's Encrypt certificate.
Certificate renewal reloads Nginx automatically. Redis is exposed only on the
server's loopback interface for the local worker's SSH tunnel. The gateway uses
Celery to publish tasks to Redis; the bot worker runs on your own machine.

View logs:

``` bash
docker compose logs -f
```

Stop containers without deleting Redis data:

``` bash
docker compose down
```

## Running the Worker

Run your local worker that contains the **aiogram bot handlers** and executes heavy processing:

``` bash
./bot_factories/echo_bot/start_worker.sh
```
The echo launcher loads its selected env file, opens an SSH tunnel to the
server's Redis, and starts the Celery worker. Stop it with Ctrl+C. The cloud
instance receives webhooks and publishes updates to the shared queue.

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
3. Create a Celery app using `CeleryFactory.create_app(router=your_router)`.
4. Give this bot its own gateway deployment and Redis broker.

The shared gateway and worker modules contain no service-specific processing code.

The FaceSwap integration test is opt-in because it requires a running local
FaceFusion HTTP service and ignored media fixtures under
`bot_factories/faceswap_bot/tests/data/`:

``` bash
RUN_FACESWAP_INTEGRATION=1 .venv/bin/pytest bot_factories/faceswap_bot/tests/test_integration.py
```

## License

MIT

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

- Python 3.13
- Docker
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

## Private admin bot and managed echo bots

`bot_factories/admin_bot` is a separate bot on the existing gateway/queue
infrastructure. Only `ADMIN_BOT_OWNER_ID` can use it, in a private chat.
The initial token is the placeholder `ххх`; nothing contacts Telegram until
configured and explicitly started.

1. Create the admin bot in BotFather and enable bot management in its Mini App.
2. Set these values in `.env` on the gateway and both worker hosts:

   ```env
   ADMIN_BOT_TOKEN=ххх
   ADMIN_BOT_OWNER_ID=123456789
   ADMIN_BOT_PUBLIC_BASE_URL=https://your-domain.com
   ADMIN_BOT_WEBHOOK_SECRET=replace-with-a-random-secret
   ```

   Replace `ххх` with the real token. `OWNER_ID` is your numeric Telegram user ID.
   Generate a webhook secret with `openssl rand -hex 32`.
   Keep the same owner ID and webhook configuration on all hosts.
3. Deploy the updated gateway. HTTPS must forward `/webhook/admin` and
   `/webhook/managed/{bot_id}` to FastAPI. Existing `/webhook` remains available.
4. Start each worker in a separate terminal:

   ```bash
   bash bot_factories/admin_bot/start_worker.sh
   bash bot_factories/echo_bot/start_managed_worker.sh
   ```

   These scripts use Redis connection settings from `.env`. For a remote Redis,
   establish a private connection/SSH tunnel first; these scripts do not create
   one. Both workers use the same Redis as the gateway.
5. Register the admin webhook:

   ```bash
   .venv/bin/python -m bot_factories.admin_bot.setup
   ```

6. Open the admin bot, send `/start`, press **Создать эхо-бота**, and complete
   Telegram's creation dialog. `/bots` lists bots; `/retry BOT_ID` retries a
   failed connection. The echo worker must be running to receive replies.

All created bots use the existing echo handlers. Text is echoed literally,
including Markdown characters. No additional process is created per bot.
Redis DB 3 stores metadata and webhook secrets, never child bot tokens; workers
fetch tokens from the manager API when needed. Restrict Redis access to trusted
hosts (workers share access to the manager token). Compose enables AOF
persistence; retain and back up its data volume. Do not use `down -v` when you
want to retain registered bots.

The adapter calls Managed Bots methods directly because the installed aiogram
version does not model them yet. See the
[Telegram Managed Bots API](https://core.telegram.org/bots/api#keyboardbuttonrequestmanagedbot).
Telegram creation/token updates reconnect the bot; ownership changes away from
the configured owner disable it locally. Duplicate creation updates overwrite
the same registry entry rather than adding another bot.

This first version has no deletion UI or delivery deduplication: a redelivered
Telegram/Celery update may produce a repeated echo. It does not add FaceSwap
multibot support.

### systemd deployment

For the existing `/opt/tgbot-queue` server installation, unit templates are in
`deploy/systemd/`. Once the admin settings are configured in the server `.env`:

```bash
sudo install -m 644 deploy/systemd/tgbot-admin.service /etc/systemd/system/
sudo install -m 644 deploy/systemd/tgbot-managed-echo.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now tgbot-admin tgbot-managed-echo
sudo systemctl restart tgbot-gateway
.venv/bin/python -m bot_factories.admin_bot.setup
```

These lightweight echo and admin workers can run on the gateway host; the
existing FaceSwap worker remains on the client machine. For a system Redis
installation, configure persistence separately (Compose settings do not apply).

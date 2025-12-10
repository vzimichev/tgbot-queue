# Telegram Processing Gateway

A lightweight FastAPI + Celery gateway designed to help you build and test Telegram bots that require heavy local processing — such as AI image/video generation, audio transcription, face-swapping, or any CPU/GPU-intensive tasks.

The idea is simple:

- Run your heavy logic locally (GPU, CPU, large models, media processing).

- Deploy only a lightweight webhook gateway in the cloud.

- The cloud instance receives Telegram updates → forwards them to your local machine → your local workers process heavy tasks → send results back to Telegram.

- This allows you to experiment with AI-powered bots without paying for expensive cloud GPUs.

## Features

- **Webhook Gateway**: Receives Telegram updates and forwards them as Celery tasks.

- **Redis Queue**: Decouples the cloud gateway from your local processing machine.

- **Celery Workers**: Run locally or remotely and handle all heavy workloads (AI, video, audio, ML pipelines).

- **Aiogram Bot Layer**: You write simple Aiogram handlers; everything else—queueing, routing, sending responses—is already wired.

- **Modular Architecture**: Each part (gateway, worker, bot logic) is isolated and easy to extend.

- **Local/Remote Hybrid Setup**:

  - Run workers with access to GPUs locally.

  - Deploy only the lightweight FastAPI gateway to a $5 cloud server.

Perfect for prototyping and experimenting with creative or AI-powered bot ideas.

## Folder Structure

    /api                 – FastAPI webhook  
    /worker              – Celery setup  
    /bot_factory         – aiogram bots (customizable)  
    /shared              – configs, clients  

If you want to build a fully customized bot, place it inside
`bot_factory`.\
Bot customization is essentially about defining **aiogram routes and
handlers**.\
The rest of the architecture (gateway → celery → worker → aiogram →
telegram API) remains unchanged.

## Requirements

- Python 3.13
- Redis
- Telegram Bot Token
- Domain name (required by Telegram)

## Configuration

Create `.env` in project root:

``` env
TELEGRAM_TOKEN=123456:ABC
WEBHOOK_SECRET_TOKEN=super-secret

REDIS_HOST=redis
REDIS_PORT=6379
REDIS_PASSWORD=guest1
```

All variables are loaded via `shared/config.py`.

# Running With Docker Compose

``` bash
docker compose up -d --build
```

This starts:

- **gateway**: FastAPI server receiving Telegram webhook calls
- **redis**: Message broker
- **flower**: Celery monitoring UI

Check logs:

``` bash
docker compose logs -f
```

Shutdown:

``` bash
docker compose down -v
```


Once gateway is running, set webhook:

https://your_domain/webhook

Use Bot API to set it:
``` bash
curl -X POST "https://api.telegram.org/bot<token>/setWebhook" \
  -d "url=https://your_domain/webhook" \
  -d "secret_token=<WEBHOOK_SECRET_TOKEN>"
```

## Running Components Manually

### FastAPI Gateway

``` bash
uvicorn api.main:app --host 0.0.0.0 --port 8000
```

### Celery Worker (with aiogram bot)

``` bash
celery -A bot_factories.echo_bot.celery_app worker --loglevel=info
```

The worker loads the aiogram bot from `bot_factory`.

# Aiogram + Celery Integration

Pipeline:

    Telegram → FastAPI → Celery Task → Redis → Worker → Aiogram Bot → Telegram API

Aiogram **does not receive webhooks directly** --- it runs inside a
Celery worker.

## Custom Bots (bot_factory)

To create a custom bot:

1.  Add a file inside `bot_factory/`.
2.  Define aiogram routers and handlers.
3.  Connect the bot in the worker if needed.
4.  No changes required to the core architecture.

## Default Worker Behavior

Default response:

    Worker response: <original message text>

Extendable for:

-   photos / videos
-   multi-step conversations
-   async AI processing
-   custom logic in aiogram

## License

MIT

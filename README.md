# Telegram Processing Gateway

A FastAPI-based gateway for receiving Telegram webhooks and delegating message processing to background workers using Celery with Redis as the broker.

## Features

- Receives Telegram updates via a webhook endpoint.
- Publishes processing tasks to Redis (Celery broker).
- Handles messages asynchronously via Celery workers.
- Provides clean architectural separation:
  - **Gateway layer** — HTTP intake from Telegram.
  - **Task layer** — publishes jobs to the queue.
  - **Worker layer** — business logic of processing messages.
  - **Telegram client layer** — sends replies back via Bot API.

## Requirements

- Python 3.13+
- Redis server
- Telegram Bot Token

## Installation

```bash
# Clone repository
git clone <repo_url>
cd tgbot-queue

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
poetry install
```

## Configuration

Create a `.env` file in the project root:

```env
REDIS_URL=redis://:<password>@<host>:6379/0

TELEGRAM_BOT_TOKEN=<your_bot_token>
```

All environment variables are loaded via `core/config.py`.

## Running the Gateway (FastAPI)

```bash
uvicorn api.main:app --host 0.0.0.0 --port 8000
```

- Webhook endpoint: `/webhook/telegram`
- Accepts standard Telegram update JSON

## Running Celery Worker

```bash
celery -A worker.celery_app.celery_app worker --loglevel=info
```

- Tasks are dispatched by the gateway.
- Workers consume tasks from Redis and execute message-processing logic.

## Architecture Overview

```
Telegram → FastAPI Webhook → Celery Task → Redis Queue → Worker → Telegram Bot API
```

### Layers

- **Gateway** (`api/`)  
  Validates and accepts Telegram updates.

- **Tasks** (`worker/tasks.py`)  
  Defines background tasks for processing incoming updates.

- **Worker** (`worker/celery_app.py`)  
  Configures Celery and runs message-processing logic.

- **Telegram Client** (`core/telegram_client.py`)  
  A lightweight wrapper around the Telegram Bot API.

## Example Task Payload

```json
{
  "update_id": 123456,
  "message": {
    "message_id": 1,
    "from": {"id": 111, "is_bot": false, "first_name": "Valery"},
    "chat": {"id": 111, "type": "private"},
    "text": "Hello"
  }
}
```

## Default Worker Behavior

For now, the worker replies with:

```
Worker response: <original message text>
```

You can extend the logic to handle photos, commands, multi-step dialogs, etc.

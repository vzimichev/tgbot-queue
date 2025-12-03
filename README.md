# Telegram Gateway

FastAPI gateway for handling Telegram webhooks and processing them asynchronously via Celery.

## Features

- Receives Telegram updates via webhooks.
- Sends tasks to RabbitMQ.
- Processes tasks asynchronously with Celery workers.
- Replies to Telegram messages automatically.

## Requirements

- Python 3.13+
- RabbitMQ server
- Telegram Bot token

## Installation

```bash
# Clone repo
git clone <repo_url>
cd tgbot-queue

# Setup virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
poetry install
```

## Configuration

Create a `.env` file in the project root:

```env
RABBITMQ_USER=<user>
RABBITMQ_PASSWORD=<password>
RABBITMQ_HOST=<host>
RABBITMQ_PORT=5672

TELEGRAM_BOT_TOKEN=<your_bot_token>
```

The project uses `core/config.py` to load settings from environment variables.

## Running FastAPI

```bash
api.main:app --host 0.0.0.0 --port 8000
```

- Webhook endpoint: `/webhook/telegram`  
- Expects Telegram updates in JSON format.

## Running Celery Worker

```bash
celery -A worker.celery_app.celery_app worker --loglevel=info
```

- The worker consumes tasks from RabbitMQ.
- Tasks are defined in `worker/tasks.py`.

## Telegram Message Processing

Tasks take the Telegram update JSON and reply with:

```
Rabbit answered: <original message text>
```

**Example JSON structure for tasks:**

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
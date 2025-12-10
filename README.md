# Telegram Processing Gateway

A **FastAPI-based gateway** for receiving Telegram webhooks and delegating message processing to background workers.
Workers can run **locally or remotely**, allowing heavy processing (like AI image/video generation) without overloading the cloud instance.

## Features

* Receives Telegram updates via a webhook endpoint.
* Publishes processing tasks to **Redis** (Celery broker).
* Handles messages asynchronously via **Celery workers**.
* Supports **pluggable processing backends**:

  * Local executable
  * Remote API or service
  * Example: FaceFusion for AI face/video processing
* Clean architectural separation:

  * **Gateway layer** — HTTP intake from Telegram.
  * **Task layer** — publishes jobs to the queue.
  * **Worker layer** — business logic for processing messages.
  * **Processor layer** — isolated heavy processing (e.g., AI models).
  * **Telegram client layer** — sends replies back via Bot API.

## Requirements

* Python 3.13+
* Redis server
* Telegram Bot Token
* Optional: GPU/CPU resources for heavy processors (local or remote)

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
# Telegram
TELEGRAM_TOKEN=123456:ABC-DEF123
WEBHOOK_SECRET_TOKEN=super-secret

# Redis
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_PASSWORD=guest1

# Processor configuration
PROCESSOR_TYPE=facefusion       # e.g., "facefusion", "dummy", "custom"
PROCESSOR_URL=http://localhost:5000  # Optional for remote API processors
PROCESSOR_EXECUTABLE=/usr/local/bin/facefusion  # Optional for local executables
```

All environment variables are loaded via `shared/config.py`.

## Running the Gateway (FastAPI)

```bash
uvicorn api.main:app --host 0.0.0.0 --port 8000
```

* Webhook endpoint: `/webhook`
* Accepts standard Telegram update JSON
* Publishes tasks to Redis for asynchronous processing

## Running Celery Worker

```bash
celery -A worker.celery_app.celery_app worker --loglevel=info
```

* Tasks are dispatched by the gateway.
* Workers consume tasks from Redis and execute **message-processing logic**.
* Worker logic can call local or remote processors depending on configuration.

## Processor Layer

The processor layer is designed to be **modular and replaceable**:

* **Local executable**:

  ```bash
  facefusion run -s <input_photo> -t <input_video> -o <output_path>
  ```
* **Remote API**:

  * Any processor exposing an HTTP interface can be connected via `PROCESSOR_URL`.
* **Dummy processor**:

  * For testing, no heavy processing is required.

## Architecture Overview

```
Telegram → FastAPI Webhook → Celery Task → Redis Queue → Worker → Processor (local/remote) → Telegram Bot API
```

### Layers

* **Gateway** (`api/`)
  Validates and accepts Telegram updates.

* **Tasks** (`worker/tasks.py`)
  Defines background tasks for processing incoming updates.

* **Worker** (`worker/celery_app.py`)
  Configures Celery and runs message-processing logic.

* **Processor** (`processors/`)
  Handles heavy processing asynchronously and in isolation.

* **Telegram Client** (`shared/telegram_client.py`)
  Sends replies and media back to Telegram via Bot API.

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

You can extend the logic to handle:

* Photos and videos
* Multi-step dialogs
* AI-based content processing
* Any other custom processors

## Contribution

* Extend the `processors/` folder with new processing modules.
* Use `PROCESSOR_TYPE` to switch between different backends.
* Keep cloud instance light — heavy workloads should stay isolated.

## License

MIT

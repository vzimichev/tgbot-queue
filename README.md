# Telegram Gateway – FastAPI Webhook Server

This service acts as a lightweight gateway between **Telegram** and your internal services.  
It receives webhook updates from Telegram, processes them, and can forward tasks to other systems.

---

## Features

- FastAPI-based webhook endpoint  
- Validates Telegram `secret_token` (optional)  
- Sends responses back using Telegram Bot API  
- Dockerized (Python 3.14 + Poetry)  
- Easy to deploy on DigitalOcean, AWS, or any VPS  
- Can integrate with message queues (RabbitMQ) or S3 for task handling  

---

## Project Structure

```
app/
  api/
    webhook.py       # Webhook controller
  services/
    telegram.py      # Telegram API client
  core/
    config.py        # Environment configuration
  main.py            # FastAPI entrypoint
Dockerfile
docker-compose.yml
README.md
.env
pyproject.toml
```

---

## Installation (Local)

### 1. Install dependencies

```bash
poetry install
```

### 2. Run the FastAPI server

```bash
poetry run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The webhook endpoint will be available at:

```
POST /webhook
```

Swagger UI:

```
http://localhost:8000/docs
```

---

## Docker Usage

### 1. Build the image

```bash
docker build -t telegram_gateway .
```

### 2. Run the container

```bash
docker run -p 8000:8000 --env-file .env telegram_gateway
```

Or using Docker Compose:

```bash
docker-compose up -d
```

---

## Environment Variables (`.env`)

```
TELEGRAM_TOKEN=123456:ABC-DEF
WEBHOOK_SECRET_TOKEN=super-secret-token
RABBITMQ_HOST=rabbitmq
RABBITMQ_PORT=5672
RABBITMQ_DEFAULT_USER=youruser
RABBITMQ_DEFAULT_PASS=yourpassword
RABBITMQ_QUEUE=telegram_updates
```

- `WEBHOOK_SECRET_TOKEN` is optional, but recommended for security.  
- RabbitMQ variables are required if integrating with message queues.

---

## Set Telegram Webhook

Replace `<TOKEN>` and `<YOUR_DOMAIN_OR_IP>`:

```bash
curl -X POST \
  https://api.telegram.org/bot<TOKEN>/setWebhook \
  -H "Content-Type: application/json" \
  -d '{
        "url": "https://<YOUR_DOMAIN_OR_IP>/webhook",
        "secret_token": "super-secret-token"
      }'
```

Expected response:

```json
{"ok":true, "result":true}
```

---

## How It Works

1. Telegram sends updates to your `/webhook` endpoint.  
2. FastAPI receives and parses the incoming update.  
3. Business logic handles the event (e.g., sends message, forwards to RabbitMQ, saves to S3).  
4. Responses are sent back to Telegram using `sendMessage()`.

---

## Example Logic (Echo Bot)

Inside `webhook.py`:

```python
await send_message(chat_id, f"You said: {text}")
```

Replace this with any logic you want: queueing, S3 uploads, analytics, etc.

---

## Notes

- Keep `.env` out of Git (`.gitignore`) to avoid leaking tokens and passwords.  
- For production, use HTTPS (TLS) for your webhook URL.  
- You can use any domain or static IP for your server; a domain is required for Telegram webhooks with TLS.
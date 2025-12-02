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

---

## Project Structure

```
app/
  api/
    webhook.py       # Webhook controller
  services/
    telegram.py      # Telegram API client
  core/
    config.py        # Environment config
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

```
poetry install
```

### 2. Run the FastAPI server

```
poetry run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The webhook endpoint will be available at:

```
POST /webhook
```

---

## Docker Usage

### Build the image

```
docker build -t telegram_gateway .
```

### Run the container

```
docker run -p 8000:8000 --env-file .env telegram_gateway
```

---

## Environment Variables (`.env`)

```
TELEGRAM_TOKEN=123456:ABC-DEF
WEBHOOK_SECRET_TOKEN=super-secret-token
```

`WEBHOOK_SECRET_TOKEN` is optional, but recommended for security.

---

## Set Telegram Webhook

Replace `<TOKEN>` and `<YOUR_DOMAIN_OR_IP>`:

```
curl -X POST \
  https://api.telegram.org/bot<TOKEN>/setWebhook \
  -H "Content-Type: application/json" \
  -d '{
        "url": "https://<YOUR_DOMAIN_OR_IP>/webhook",
        "secret_token": "super-secret-token"
      }'
```

You should get:

```
{"ok":true, "result":true}
```

---

## How It Works

1. Telegram sends updates to your `/webhook` endpoint  
2. FastAPI receives and parses the incoming update  
3. Business logic handles the event  
4. Responses are sent back to Telegram using `sendMessage()`

---

## Example Logic (Echo Bot)

Inside `webhook.py`:

```python
await send_message(chat_id, f"You said: {text}")
```

Replace this with any logic you want (integrations, queues, S3 uploads, etc.).

---


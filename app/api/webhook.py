from fastapi import APIRouter, Request, Header
from app.services.telegram import send_message
from app.core.config import settings

router = APIRouter()


@router.post("/webhook")
async def telegram_webhook(
    request: Request,
    telegram_secret_token: str | None = Header(None)
):
    if settings.webhook_secret_token and \
       telegram_secret_token != settings.webhook_secret_token:
        return {"status": "forbidden"}

    update = await request.json()

    message = update.get("message")
    if not message:
        return {"ok": True}

    chat_id = message["chat"]["id"]
    text = message.get("text", "")

    # sample answer
    await send_message(chat_id, f"You said: {text}")

    return {"ok": True}

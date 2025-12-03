import httpx

from core.config import settings

TELEGRAM_API = f"https://api.telegram.org/bot{settings.telegram_token}"


def send_message(chat_id: int, text: str):
    with httpx.Client(timeout=20) as client:
        client.post(
            f"{TELEGRAM_API}/sendMessage",
            json={"chat_id": chat_id, "text": text},
        )

import httpx

from core.config import settings

TELEGRAM_API = f"https://api.telegram.org/bot{settings.telegram_token}"


async def send_message(chat_id: int, text: str):
    async with httpx.AsyncClient() as client:
        await client.post(
            f"{TELEGRAM_API}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=20,
        )

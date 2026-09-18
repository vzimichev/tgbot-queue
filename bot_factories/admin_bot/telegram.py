"""Raw Bot API calls also support managed bots on older aiogram versions."""

import logging

import httpx


class TelegramAPI:
    def __init__(self, token):
        self.token = token

    def call(self, method, **payload):
        # HTTP client logs include the request URL, which contains the bot token.
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)
        try:
            response = httpx.post(
                f"https://api.telegram.org/bot{self.token}/{method}",
                json=payload,
                timeout=30,
            )
            data = response.json()
            if response.is_success and data.get("ok"):
                return data["result"]
        except (httpx.HTTPError, ValueError):
            pass
        # Never propagate exceptions containing credential-bearing URLs.
        raise RuntimeError(f"Telegram API call failed: {method}") from None

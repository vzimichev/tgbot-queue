"""Small adapter for Managed Bots, not yet modeled by our aiogram version."""

import aiohttp
import ssl
import certifi


class TelegramAPIError(RuntimeError):
    pass


async def telegram_call(token, method, **payload):
    # Do not propagate transport exceptions: their URLs can contain bot tokens.
    try:
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
            connector=aiohttp.TCPConnector(
                ssl=ssl.create_default_context(cafile=certifi.where())
            ),
        ) as session:
            async with session.post(
                f"https://api.telegram.org/bot{token}/{method}", json=payload
            ) as response:
                result = await response.json()
                if response.status != 200 or not result.get("ok"):
                    raise TelegramAPIError(f"Telegram {method} failed")
                return result["result"]
    except (aiohttp.ClientError, TimeoutError, ValueError):
        raise TelegramAPIError(f"Telegram {method} request failed") from None

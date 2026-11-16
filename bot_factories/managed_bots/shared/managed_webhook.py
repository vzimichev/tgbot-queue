import hashlib
import hmac


def managed_bot_webhook_secret(secret: str, bot_id: int) -> str:
    """Return a deterministic, Telegram-compatible webhook secret for one bot."""
    return hmac.new(secret.encode(), str(bot_id).encode(), hashlib.sha256).hexdigest()

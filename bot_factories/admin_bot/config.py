import os

from pydantic_settings import BaseSettings


class AdminBotSettings(BaseSettings):
    token: str | None = None
    owner_id: int = 0
    child_webhook_url: str | None = None
    faceswap_api_base_url: str = "http://127.0.0.1:8001"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        env_prefix = "ADMIN_BOT_"
        extra = "ignore"


admin_bot_settings = AdminBotSettings(_env_file=os.getenv("APP_ENV_FILE", ".env"))

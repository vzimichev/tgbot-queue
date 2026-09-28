import os

from pydantic_settings import BaseSettings


class AdminBotSettings(BaseSettings):
    token: str | None = None
    owner_id: int = 0

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        env_prefix = "ADMIN_BOT_"
        extra = "ignore"


def get_admin_bot_settings() -> AdminBotSettings:
    return AdminBotSettings(_env_file=os.getenv("APP_ENV_FILE", ".env"))

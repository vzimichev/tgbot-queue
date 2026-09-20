import os
from typing import Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Telegram
    telegram_token: Optional[str] = None
    webhook_secret_token: Optional[str] = None

    # Redis
    redis_host: str = "redis"
    redis_port: int = 6379
    redis_password: Optional[str] = None

    telegram_request_timeout: float = 600.0

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings(_env_file=os.getenv("APP_ENV_FILE", ".env"))

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

    # Worker routing selected by this gateway deployment
    telegram_task_name: str = "echo_bot.process_telegram_update"
    telegram_queue: str = "echo_bot"
    telegram_request_timeout: float = 600.0

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()

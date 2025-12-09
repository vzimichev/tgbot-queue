from pydantic import BaseSettings
from typing import Optional, Literal


class Settings(BaseSettings):
    # Telegram
    telegram_token: str
    webhook_secret_token: Optional[str] = None

    # Redis
    redis_host: str = "redis"
    redis_port: int = 6379
    redis_password: Optional[str] = None

    # Processor provider
    processor_type: Literal["facefusion", "remote", "dummy"] = "facefusion"
    processor_url: Optional[str] = None

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()

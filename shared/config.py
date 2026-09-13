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

    # Local FaceFusion HTTP service
    faceswap_api_url: str = "http://127.0.0.1:8001/run"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()

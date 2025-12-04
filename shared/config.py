from typing import Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Telegram
    telegram_token: str
    webhook_secret_token: Optional[str] = None

    # Redis
    redis_host: str
    redis_port: int
    redis_password: str

    class Config:
        env_file = ".env"


settings = Settings()

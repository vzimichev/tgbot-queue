from typing import Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    telegram_token: str
    webhook_secret_token: Optional[str] = None

    class Config:
        env_file = ".env"


settings = Settings()

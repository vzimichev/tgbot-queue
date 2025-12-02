from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    telegram_token: str
    webhook_secret_token: str | None = None  # опционально

    class Config:
        env_file = ".env"


settings = Settings()

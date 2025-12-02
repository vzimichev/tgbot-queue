from typing import Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Telegram
    telegram_token: str
    webhook_secret_token: Optional[str] = None

    # RabbitMQ
    rabbitmq_host: str
    rabbitmq_port: int
    rabbitmq_default_user: str
    rabbitmq_default_password: str
    rabbitmq_queue: str

    class Config:
        env_file = ".env"


settings = Settings()

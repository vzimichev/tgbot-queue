from typing import Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Telegram
    telegram_token: str
    webhook_secret_token: Optional[str] = None

    # RabbitMQ
    rabbitmq_host: str = "rabbitmq"
    rabbitmq_port: int = 5672
    rabbitmq_user: str = "guest"
    rabbitmq_password: str = "guest"
    rabbitmq_queue: str = "telegram_updates"

    class Config:
        env_file = ".env"


settings = Settings()

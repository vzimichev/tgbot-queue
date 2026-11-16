import os

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ManagedBotsSettings(BaseSettings):
    token: str | None = Field(default=None, validation_alias="ADMIN_BOT_TOKEN")
    owner_id: int = Field(default=0, validation_alias="ADMIN_BOT_OWNER_ID")
    child_webhook_url: str | None = Field(
        default=None, validation_alias="ADMIN_BOT_CHILD_WEBHOOK_URL"
    )
    webhook_secret_token: str | None = None
    sqs_region: str | None = None
    sqs_queue_url: str | None = None
    telegram_request_timeout: float = 600.0

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = ManagedBotsSettings(_env_file=os.getenv("APP_ENV_FILE", ".env"))

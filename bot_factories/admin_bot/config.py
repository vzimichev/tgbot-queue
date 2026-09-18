from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class AdminBotSettings(BaseSettings):
    token: SecretStr = SecretStr("")
    owner_id: int = 0
    public_base_url: str = ""
    webhook_secret: SecretStr = SecretStr("")

    model_config = SettingsConfigDict(
        env_file=".env", env_prefix="ADMIN_BOT_", extra="ignore"
    )


admin_settings = AdminBotSettings()

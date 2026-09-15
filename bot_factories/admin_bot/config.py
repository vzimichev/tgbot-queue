from pydantic_settings import BaseSettings, SettingsConfigDict


class AdminSettings(BaseSettings):
    token: str = "ххх"
    owner_id: int = 0
    public_base_url: str = ""
    webhook_secret: str = ""

    model_config = SettingsConfigDict(
        env_file=".env", env_prefix="ADMIN_BOT_", extra="ignore"
    )

    def validate_runtime(self):
        if self.token in ("ххх", "xxx", "") or self.owner_id <= 0:
            raise ValueError("Set ADMIN_BOT_TOKEN and ADMIN_BOT_OWNER_ID in .env")
        if not self.public_base_url.startswith("https://") or not self.webhook_secret:
            raise ValueError(
                "Set HTTPS ADMIN_BOT_PUBLIC_BASE_URL and ADMIN_BOT_WEBHOOK_SECRET"
            )


admin_settings = AdminSettings()

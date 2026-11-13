from bot_factories.admin_bot.config import AdminBotSettings


def test_admin_bot_settings_reads_prefixed_environment(monkeypatch):
    monkeypatch.setenv("ADMIN_BOT_TOKEN", "123:token")
    monkeypatch.setenv("ADMIN_BOT_OWNER_ID", "42")
    monkeypatch.setenv("ADMIN_BOT_CHILD_WEBHOOK_URL", "https://example.test/managed")

    settings = AdminBotSettings(_env_file=None)

    assert settings.token == "123:token"
    assert settings.owner_id == 42
    assert settings.child_webhook_url == "https://example.test/managed"

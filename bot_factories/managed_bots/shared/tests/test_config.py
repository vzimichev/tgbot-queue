from bot_factories.managed_bots.shared.config import ManagedBotsSettings


def test_settings_reads_prefixed_environment(monkeypatch):
    monkeypatch.setenv("ADMIN_BOT_TOKEN", "123:token")
    monkeypatch.setenv("ADMIN_BOT_OWNER_ID", "42")
    monkeypatch.setenv("ADMIN_BOT_CHILD_WEBHOOK_URL", "https://example.test/managed")
    monkeypatch.setenv("SQS_REGION", "eu-central-1")
    monkeypatch.setenv("SQS_QUEUE_URL", "https://sqs.example/updates")
    monkeypatch.setenv("WEBHOOK_SECRET_TOKEN", "test-secret")
    monkeypatch.setenv("TELEGRAM_REQUEST_TIMEOUT", "45")
    monkeypatch.setenv("TELEGRAM_TOKEN", "unused-token")

    settings = ManagedBotsSettings(_env_file=None)

    assert settings.token == "123:token"
    assert settings.owner_id == 42
    assert settings.child_webhook_url == "https://example.test/managed"
    assert settings.sqs_region == "eu-central-1"
    assert settings.sqs_queue_url == "https://sqs.example/updates"
    assert settings.webhook_secret_token == "test-secret"
    assert settings.telegram_request_timeout == 45

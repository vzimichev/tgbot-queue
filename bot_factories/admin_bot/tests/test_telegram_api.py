from unittest.mock import Mock

import httpx
import pytest

from bot_factories.admin_bot import telegram_api


def response(*, ok=True, result=True, status_code=200, description="bad"):
    value = Mock(is_success=ok, status_code=status_code)
    value.json.return_value = {"ok": ok, "result": result, "description": description}
    return value


def test_get_managed_bot_token_validates_input_and_response(monkeypatch):
    monkeypatch.setattr(telegram_api, "_admin_bot_token", lambda: "admin")
    post = Mock(return_value=response(result="child"))
    monkeypatch.setattr(telegram_api.httpx, "post", post)

    assert telegram_api.get_managed_bot_token(99) == "child"
    assert post.call_args.args[0].endswith("/getManagedBotToken")
    with pytest.raises(ValueError):
        telegram_api.get_managed_bot_token(0)


def test_webhook_configuration_uses_child_secret(monkeypatch):
    monkeypatch.setattr(telegram_api.admin_bot_settings, "child_webhook_url", "https://host/hook/")
    monkeypatch.setattr(telegram_api.settings, "webhook_secret_token", "gateway")
    call = Mock(return_value=True)
    monkeypatch.setattr(telegram_api, "_call", call)

    telegram_api.configure_managed_bot_webhook("child", 99)

    assert call.call_args.args == ("child", "setWebhook")
    assert call.call_args.kwargs["url"] == "https://host/hook/99"
    assert call.call_args.kwargs["allowed_updates"] == ["message"]


def test_api_errors_redact_token_and_urls(monkeypatch):
    monkeypatch.setattr(
        telegram_api.httpx,
        "post",
        Mock(return_value=response(ok=False, status_code=400, description="bad secret https://host/?x=1")),
    )

    with pytest.raises(RuntimeError) as caught:
        telegram_api._call("secret", "method")

    assert "secret" not in str(caught.value)
    assert "https://" not in str(caught.value)
    assert "code=400" in str(caught.value)


def test_network_errors_are_wrapped(monkeypatch):
    monkeypatch.setattr(telegram_api.httpx, "post", Mock(side_effect=httpx.ConnectError("no")))

    with pytest.raises(RuntimeError, match="method"):
        telegram_api._call("token", "method")

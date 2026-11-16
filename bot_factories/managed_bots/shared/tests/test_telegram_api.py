from unittest.mock import Mock

import httpx
import pytest

from bot_factories.managed_bots.shared import telegram_api


def response(*, ok=True, result=True, status_code=200, description="bad"):
    value = Mock(is_success=ok, status_code=status_code)
    value.json.return_value = {"ok": ok, "result": result, "description": description}
    return value


def test_get_managed_bot_token_validates_input_and_response(monkeypatch):
    post = Mock(return_value=response(result="child"))
    monkeypatch.setattr(telegram_api.httpx, "post", post)

    assert telegram_api.get_managed_bot_token(99, admin_token="admin") == "child"
    assert post.call_args.args[0].endswith("/getManagedBotToken")
    with pytest.raises(ValueError):
        telegram_api.get_managed_bot_token(0, admin_token="admin")


def test_webhook_configuration_uses_child_secret(monkeypatch):
    call = Mock(return_value=True)
    monkeypatch.setattr(telegram_api, "_call", call)

    telegram_api.configure_managed_bot_webhook(
        "child",
        99,
        child_webhook_url="https://host/hook/",
        webhook_secret_token="gateway",
    )

    assert call.call_args.args == ("child", "setWebhook")
    assert call.call_args.kwargs["url"] == "https://host/hook/99"
    assert call.call_args.kwargs["allowed_updates"] == ["message"]


def test_commands_configuration_uses_child_token(monkeypatch):
    call = Mock(return_value=True)
    monkeypatch.setattr(telegram_api, "_call", call)

    telegram_api.configure_managed_bot_commands("child")

    assert call.call_args.args == ("child", "setMyCommands")
    assert call.call_args.kwargs["commands"] == [
        {"command": "balance", "description": "Show remaining limit"},
        {"command": "transactions", "description": "Show recent transactions"},
    ]


def test_client_uses_its_own_credentials_and_webhook_settings(monkeypatch):
    call = Mock(return_value="child")
    monkeypatch.setattr(telegram_api, "_call", call)
    first = telegram_api.ManagedBotTelegramApi(
        admin_token="first",
        child_webhook_url="https://first/hook",
        webhook_secret_token="first-secret",
    )
    second = telegram_api.ManagedBotTelegramApi(
        admin_token="second",
        child_webhook_url="https://second/hook",
        webhook_secret_token="second-secret",
    )

    assert first.get_managed_bot_token(99) == "child"
    assert call.call_args.args == ("first", "getManagedBotToken")
    second.set_access_open(99)
    assert call.call_args.args == ("second", "setManagedBotAccessSettings")
    first.configure_child_webhook("child", 99)
    assert call.call_args.kwargs["url"] == "https://first/hook/99"
    assert call.call_args.kwargs["secret_token"] == (
        telegram_api.managed_bot_webhook_secret("first-secret", 99)
    )


def test_api_errors_redact_token_and_urls(monkeypatch):
    monkeypatch.setattr(
        telegram_api.httpx,
        "post",
        Mock(
            return_value=response(
                ok=False, status_code=400, description="bad secret https://host/?x=1"
            )
        ),
    )

    with pytest.raises(RuntimeError) as caught:
        telegram_api._call("secret", "method")

    assert "secret" not in str(caught.value)
    assert "https://" not in str(caught.value)
    assert "code=400" in str(caught.value)


def test_network_errors_are_wrapped(monkeypatch):
    monkeypatch.setattr(
        telegram_api.httpx, "post", Mock(side_effect=httpx.ConnectError("no"))
    )

    with pytest.raises(RuntimeError, match="method"):
        telegram_api._call("token", "method")

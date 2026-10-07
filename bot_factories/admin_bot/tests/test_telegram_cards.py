from urllib.parse import parse_qs, urlsplit

import pytest

from bot_factories.admin_bot.db.managed_bots import ManagedBotStatus
from bot_factories.admin_bot.telegram_cards import (
    bot_card_keyboard,
    bot_card_text,
    bot_link,
    invitation_button,
    main_menu_keyboard,
    managed_bot_creation_card,
    parse_limit_action,
    user_card,
)


def test_main_menu_requests_exactly_one_human_user():
    request = main_menu_keyboard().keyboard[0][0].request_users

    assert request.max_quantity == 1
    assert request.user_is_bot is False
    assert request.request_username is True


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("limit:7:10", (7, 10)),
        ("limit:7:custom", (7, None)),
        ("limit:7:11", None),
        ("limit:x:10", None),
        ("other:7:10", None),
        (None, None),
    ],
)
def test_parse_limit_action(value, expected):
    assert parse_limit_action(value) == expected


def test_pending_creation_card_preserves_suggested_bot_details(managed_bot):
    card = managed_bot_creation_card(managed_bot(telegram_bot_id=None), 123)
    request = card.reply_markup.keyboard[0][0].request_managed_bot

    assert request.request_id == 123
    assert request.suggested_username == "personal_bot"
    assert request.suggested_name == "Personal bot"


def test_cards_show_status_limit_and_activation_link(managed_bot):
    bot = managed_bot(claim_token="claim", status=ManagedBotStatus.AWAITING_ACTIVATION)

    assert "Awaiting activation" in bot_card_text(bot)
    assert bot_link(bot).endswith("claim_claim")
    assert user_card(7, "recipient", "Recipient", bot).reply_markup
    assert bot_card_keyboard(bot).inline_keyboard[1][0].callback_data == "limit:1:10"


def test_invitation_targets_username_or_uses_share_link(managed_bot):
    direct = invitation_button(managed_bot())
    assert urlsplit(direct.url).path == "/recipient"
    assert "personal_bot" in parse_qs(urlsplit(direct.url).query)["text"][0]

    shared = invitation_button(managed_bot(recipient_username=None))
    assert urlsplit(shared.url).path == "/share/url"
    assert parse_qs(urlsplit(shared.url).query)["url"] == ["https://t.me/personal_bot"]

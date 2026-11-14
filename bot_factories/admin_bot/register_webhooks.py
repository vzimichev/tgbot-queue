"""Re-register managed-bot webhooks after a gateway migration or secret rotation."""

from __future__ import annotations

import argparse
from dataclasses import dataclass

from bot_factories.admin_bot.repositories.bot_manager import ManagedBotsRepository
from bot_factories.admin_bot.telegram_api import ManagedBotTelegramApi


@dataclass(frozen=True)
class RegistrationSummary:
    registered: int
    skipped: int
    failed: int


def register_existing_webhooks(
    repository: ManagedBotsRepository,
    telegram_api: ManagedBotTelegramApi,
    *,
    dry_run: bool = False,
) -> RegistrationSummary:
    """Set the configured webhook on each managed bot with a Telegram bot ID.

    The child token is read from the persisted admin database. It is never
    printed. A missing persisted token is fetched through the admin bot API,
    which supports managed bots created before token persistence was added.
    """

    registered = skipped = failed = 0
    for bot in repository.list_bots():
        if bot.telegram_bot_id is None:
            skipped += 1
            print(f"skip managed bot {bot.id}: no Telegram bot ID")
            continue

        if dry_run:
            registered += 1
            print(f"would register managed bot {bot.id}")
            continue

        try:
            token = bot.child_bot_token or telegram_api.get_managed_bot_token(
                bot.telegram_bot_id
            )
            telegram_api.configure_child_webhook(token, bot.telegram_bot_id)
        except RuntimeError as error:
            failed += 1
            print(f"failed managed bot {bot.id}: {error}")
        else:
            registered += 1
            print(f"registered managed bot {bot.id}")

    return RegistrationSummary(
        registered=registered,
        skipped=skipped,
        failed=failed,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="list managed bots that would be registered without calling Telegram",
    )
    args = parser.parse_args()

    summary = register_existing_webhooks(
        ManagedBotsRepository(), ManagedBotTelegramApi(), dry_run=args.dry_run
    )
    print(
        "summary: "
        f"registered={summary.registered} skipped={summary.skipped} "
        f"failed={summary.failed}"
    )
    if summary.failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

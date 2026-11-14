"""Sequential consumer for the managed-bot SQS ingress contract."""

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger(__name__)


async def main() -> None:
    import boto3

    from bot_factories.managed_bot.tasks import dispatch_managed_update
    from shared.config import settings

    if not settings.sqs_queue_url or not settings.sqs_region:
        raise ValueError("SQS_QUEUE_URL and SQS_REGION are required")

    sqs = boto3.client("sqs", region_name=settings.sqs_region)
    await asyncio.to_thread(
        sqs.get_queue_attributes,
        QueueUrl=settings.sqs_queue_url,
        AttributeNames=["VisibilityTimeout"],
    )
    logger.info("Managed JSON worker ready.")
    while True:
        try:
            await consume_once(sqs, settings.sqs_queue_url, dispatch_managed_update)
        except Exception as error:
            logger.error("Managed SQS polling failed (%s)", type(error).__name__)
            await asyncio.sleep(5)


async def consume_once(
    sqs: Any,
    queue_url: str,
    dispatch: Callable[[int, dict[str, Any]], Awaitable[dict[str, str]]],
) -> None:
    response = await asyncio.to_thread(
        sqs.receive_message,
        QueueUrl=queue_url,
        MaxNumberOfMessages=1,
        WaitTimeSeconds=20,
    )
    for message in response.get("Messages", []):
        try:
            body = json.loads(message["Body"])
            bot_id = body.get("bot_id") if isinstance(body, dict) else None
            update = body.get("update") if isinstance(body, dict) else None
            if (
                type(bot_id) is not int
                or bot_id <= 0
                or not isinstance(update, dict)
                or type(update.get("update_id")) is not int
            ):
                raise ValueError("Expected managed bot_id and Telegram update")
            await dispatch(bot_id, update)
            await asyncio.to_thread(
                sqs.delete_message,
                QueueUrl=queue_url,
                ReceiptHandle=message["ReceiptHandle"],
            )
        except Exception as error:
            logger.error(
                "Managed update processing failed (%s); message retained",
                type(error).__name__,
            )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())

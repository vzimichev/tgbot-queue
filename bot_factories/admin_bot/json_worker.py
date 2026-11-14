"""Sequential consumer of raw Telegram updates from the admin SQS queue."""

import asyncio
import json
import logging

logger = logging.getLogger(__name__)


async def main():
    import boto3
    from aiogram import Bot, Dispatcher
    from aiogram.client.default import DefaultBotProperties
    from aiogram.client.session.aiohttp import AiohttpSession
    from aiogram.enums import ParseMode

    from bot_factories.admin_bot.routes.admin_bot import admin_router
    from shared.config import settings

    if not settings.sqs_queue_url or not settings.sqs_region:
        raise ValueError("SQS_QUEUE_URL and SQS_REGION are required")

    sqs = boto3.client("sqs", region_name=settings.sqs_region)
    await asyncio.to_thread(
        sqs.get_queue_attributes,
        QueueUrl=settings.sqs_queue_url,
        AttributeNames=["VisibilityTimeout"],
    )
    bot = Bot(
        token=settings.telegram_token,
        session=AiohttpSession(timeout=settings.telegram_request_timeout),
        default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN),
    )
    dispatcher = Dispatcher()
    dispatcher.include_router(admin_router)

    async def dispatch(body):
        from aiogram.types import Update

        await dispatcher.feed_update(bot, Update.model_validate(body))

    try:
        logger.info("Admin JSON worker ready.")
        while True:
            try:
                await consume_once(sqs, settings.sqs_queue_url, dispatch)
            except Exception as error:
                # Do not log payloads, Telegram URLs or tokens from exceptions.
                logger.error("SQS polling failed (%s)", type(error).__name__)
                await asyncio.sleep(5)
    finally:
        await bot.session.close()


async def consume_once(sqs, queue_url, dispatch):
    response = await asyncio.to_thread(
        sqs.receive_message,
        QueueUrl=queue_url,
        MaxNumberOfMessages=1,
        WaitTimeSeconds=20,
    )
    for message in response.get("Messages", []):
        try:
            body = json.loads(message["Body"])
            if (
                not isinstance(body, dict)
                or type(body.get("update_id")) is not int
            ):
                raise ValueError("Expected a Telegram update object")
            await dispatch(body)
            await asyncio.to_thread(
                sqs.delete_message,
                QueueUrl=queue_url,
                ReceiptHandle=message["ReceiptHandle"],
            )
        except Exception as error:
            logger.error("Update processing failed (%s); message retained", type(error).__name__)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())

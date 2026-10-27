from typing import Optional

from aiogram import Bot, Dispatcher, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from celery import Celery

from shared.config import settings
from worker.celery_tasks import register_default_telegram_task

TELEGRAM_UPDATE_TASK = "telegram.process_update"
TELEGRAM_UPDATE_QUEUE = (
    settings.sqs_queue_name
    if settings.celery_broker.lower() == "sqs"
    else "telegram_updates"
)


def _broker_configuration() -> tuple[str, dict]:
    broker = settings.celery_broker.lower()
    if broker == "redis":
        return (
            f"redis://:{settings.redis_password}@{settings.redis_host}:{settings.redis_port}/1",
            {},
        )

    if broker != "sqs":
        raise ValueError("CELERY_BROKER must be either 'redis' or 'sqs'")

    if not settings.sqs_region or not settings.sqs_queue_url:
        raise ValueError(
            "SQS_REGION and SQS_QUEUE_URL are required when CELERY_BROKER=sqs"
        )

    # predefined_queues makes Kombu use this queue only; it will not attempt
    # to create SQS infrastructure. Credentials deliberately stay out of this
    # configuration so boto3 uses its normal AWS credential provider chain.
    return (
        "sqs://",
        {
            "region": settings.sqs_region,
            "polling_interval": settings.sqs_polling_interval,
            "visibility_timeout": settings.sqs_visibility_timeout,
            "wait_time_seconds": 20,
            "predefined_queues": {
                settings.sqs_queue_name: {"url": settings.sqs_queue_url}
            },
        },
    )


class CeleryFactory:
    @staticmethod
    def create_app(router: Optional[Router] = None) -> Celery:
        broker_url, broker_transport_options = _broker_configuration()
        celery_app = Celery(
            "worker",
            broker=broker_url,
            backend=f"redis://:{settings.redis_password}@{settings.redis_host}:{settings.redis_port}/2",
        )

        celery_app.conf.broker_transport_options = broker_transport_options
        celery_app.conf.task_acks_late = True
        celery_app.conf.worker_prefetch_multiplier = 1
        celery_app.conf.task_serializer = "json"
        celery_app.conf.result_serializer = "json"
        celery_app.conf.accept_content = ["json"]
        if settings.celery_broker.lower() == "redis":
            celery_app.conf.broker_heartbeat = 30
        celery_app.conf.broker_connection_retry_on_startup = True

        # The gateway only needs a Celery producer. Telegram runtime objects
        # belong exclusively to concrete bot workers.
        if router is None:
            return celery_app

        celery_app.conf.task_default_queue = TELEGRAM_UPDATE_QUEUE

        bot = Bot(
            token=settings.telegram_token,
            session=AiohttpSession(timeout=settings.telegram_request_timeout),
            default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN),
        )

        dp = Dispatcher(bot=bot)
        dp.include_router(router)

        celery_app.bot = bot
        celery_app.dp = dp

        register_default_telegram_task(celery_app, task_name=TELEGRAM_UPDATE_TASK)

        return celery_app

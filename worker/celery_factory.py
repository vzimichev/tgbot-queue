from typing import Optional

from aiogram import Bot, Dispatcher, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from celery import Celery

from shared.config import settings
from worker.celery_tasks import register_default_telegram_task


class CeleryFactory:
    @staticmethod
    def create_app(
        router: Optional[Router] = None,
    ) -> Celery:
        celery_app = Celery(
            "worker",
            broker=f"redis://:{settings.redis_password}@{settings.redis_host}:{settings.redis_port}/1",
            backend=f"redis://:{settings.redis_password}@{settings.redis_host}:{settings.redis_port}/2",
        )

        celery_app.conf.task_acks_late = True
        celery_app.conf.worker_prefetch_multiplier = 1
        celery_app.conf.task_serializer = "json"
        celery_app.conf.result_serializer = "json"
        celery_app.conf.accept_content = ["json"]
        celery_app.conf.broker_heartbeat = 30
        celery_app.conf.broker_connection_retry_on_startup = True

        bot = Bot(
            token=settings.telegram_token,
            default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN),
        )

        dp = Dispatcher(bot=bot)
        if router:
            dp.include_router(router)

        celery_app.bot = bot
        celery_app.dp = dp

        register_default_telegram_task(celery_app)

        return celery_app

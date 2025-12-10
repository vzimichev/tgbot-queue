from aiogram import Dispatcher, Router
from celery import Celery

from shared.config import settings
from worker.tasks import register_default_telegram_task


class CeleryFactory:
    @staticmethod
    def create_app(
        router: Router,
        # extra_task_modules: list[str] | None = None,
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

        # modules = ["worker.celery_tasks"]
        # if extra_task_modules:
        #     modules.extend(extra_task_modules)
        #
        # celery_app.autodiscover_tasks(modules)

        dp = Dispatcher()
        dp.include_router(router)

        celery_app.dp = dp

        register_default_telegram_task(celery_app)

        return celery_app

        return celery_app

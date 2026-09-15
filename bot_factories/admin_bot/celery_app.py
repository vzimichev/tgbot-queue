import asyncio

from bot_factories.admin_bot.service import AdminService
from shared.bot_registry import ADMIN_QUEUE, ADMIN_TASK
from worker.celery_factory import CeleryFactory

celery_app = CeleryFactory.create_app()
celery_app.conf.task_default_queue = ADMIN_QUEUE


@celery_app.task(name=ADMIN_TASK)
def process_telegram_update(body):
    asyncio.run(AdminService().handle(body))

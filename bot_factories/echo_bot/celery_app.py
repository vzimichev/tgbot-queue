from bot_factories.echo_bot.telegram_routes import echo_router
from shared.config import settings
from worker.celery_factory import CeleryFactory

celery_app = CeleryFactory.create_app(
    router=echo_router,
    task_name=settings.telegram_task_name,
    queue_name=settings.telegram_queue,
)

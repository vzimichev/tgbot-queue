from bot_factories.faceswap_bot.telegram_routes import faceswap_router
from worker.celery_factory import CeleryFactory

celery_app = CeleryFactory.create_app(
    router=faceswap_router,
    task_name="faceswap_bot.process_telegram_update",
    queue_name="faceswap_bot",
)

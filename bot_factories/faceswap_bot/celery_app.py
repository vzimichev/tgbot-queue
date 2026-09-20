from bot_factories.faceswap_bot.telegram_routes import faceswap_router
from worker.celery_factory import CeleryFactory

celery_app = CeleryFactory.create_app(router=faceswap_router)

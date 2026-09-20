from bot_factories.admin_bot.telegram_routes import admin_router
from worker.celery_factory import CeleryFactory

celery_app = CeleryFactory.create_app(router=admin_router)

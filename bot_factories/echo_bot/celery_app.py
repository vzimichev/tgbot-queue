from bot_factories.echo_bot.telegram_routes import echo_router
from worker.celery_factory import CeleryFactory

celery_app = CeleryFactory.create_app(router=echo_router)

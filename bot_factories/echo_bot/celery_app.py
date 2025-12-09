from bot_factories.echo_bot.tasks import create_process_telegram_task
from bot_factories.echo_bot.telegram_routes import echo_router
from worker.celery_factory import CeleryFactory
from worker.telegram_client import dp

# Добавляем роутер плагина в общий Dispatcher
dp.include_router(echo_router)

# Создаём celery_app и автоматически ищем задачи плагина
celery_app = CeleryFactory.create_app()
celery_app.autodiscover_tasks(["bot_factories.echo_bot.tasks"])

# Регистрируем общую таску с конкретным dp
create_process_telegram_task(celery_app, dp)
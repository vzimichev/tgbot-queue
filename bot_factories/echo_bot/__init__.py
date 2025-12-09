from worker.celery_factory import CeleryFactory

celery_app = CeleryFactory.create_app(
    extra_task_modules=["bot_factories.echo_bot.tasks"]
)

"""Legacy Celery integration for local managed-bot task execution only."""

from celery import Celery

celery_app = Celery("managed_bot")
celery_app.conf.imports = ("bot_factories.managed_bot.tasks",)

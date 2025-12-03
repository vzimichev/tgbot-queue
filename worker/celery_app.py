from celery import Celery

from core.config import settings

celery_app = Celery(
    "worker",
    broker=f"amqp://{settings.rabbitmq_user}:{settings.rabbitmq_password}@{settings.rabbitmq_host}:{settings.rabbitmq_port}/",
    backend=None,
)

celery_app.conf.task_acks_late = True
celery_app.conf.worker_prefetch_multiplier = 1
celery_app.conf.task_serializer = "json"
celery_app.conf.result_serializer = "json"
celery_app.conf.accept_content = ["json"]
celery_app.conf.broker_heartbeat = 30
celery_app.conf.broker_connection_retry_on_startup = True

import worker.tasks

import unittest
from unittest.mock import patch

from aiogram import Router

from shared.config import settings
from worker.celery_factory import (
    CeleryFactory,
    TELEGRAM_UPDATE_QUEUE,
    TELEGRAM_UPDATE_TASK,
)


class CeleryFactoryTest(unittest.TestCase):
    def test_producer_does_not_create_telegram_runtime(self):
        app = CeleryFactory.create_app()

        self.assertFalse(hasattr(app, "bot"))
        self.assertFalse(hasattr(app, "dp"))

    def test_redis_is_the_default_broker(self):
        app = CeleryFactory.create_app()

        self.assertEqual(
            app.conf.broker_url,
            f"redis://:{settings.redis_password}@{settings.redis_host}:{settings.redis_port}/1",
        )
        self.assertEqual(app.conf.broker_transport_options, {})
        self.assertIsNone(app.conf.result_backend)
        self.assertTrue(app.conf.task_ignore_result)

    def test_sqs_uses_existing_queue_without_a_result_backend(self):
        with (
            patch.object(settings, "celery_broker", "sqs"),
            patch.object(settings, "sqs_region", "eu-central-1"),
            patch.object(settings, "sqs_queue_name", "telegram_updates"),
            patch.object(
                settings,
                "sqs_queue_url",
                "https://sqs.eu-central-1.amazonaws.com/123456789012/telegram_updates",
            ),
            patch.object(settings, "sqs_polling_interval", 2.0),
            patch.object(settings, "sqs_visibility_timeout", 7200),
        ):
            app = CeleryFactory.create_app()

        self.assertEqual(app.conf.broker_url, "sqs://")
        self.assertIsNone(app.conf.result_backend)
        self.assertTrue(app.conf.task_ignore_result)
        self.assertEqual(
            app.conf.broker_transport_options,
            {
                "region": "eu-central-1",
                "polling_interval": 2.0,
                "visibility_timeout": 7200,
                "wait_time_seconds": 20,
                "predefined_queues": {
                    "telegram_updates": {
                        "url": "https://sqs.eu-central-1.amazonaws.com/123456789012/telegram_updates"
                    }
                },
            },
        )

    def test_sqs_requires_region_and_existing_queue_url(self):
        with patch.object(settings, "celery_broker", "sqs"), patch.object(
            settings, "sqs_region", None
        ), patch.object(settings, "sqs_queue_url", None):
            with self.assertRaisesRegex(ValueError, "SQS_REGION and SQS_QUEUE_URL"):
                CeleryFactory.create_app()

    def test_worker_registers_shared_task_and_queue(self):
        with patch.object(settings, "telegram_token", "123456:ABCDEF"):
            app = CeleryFactory.create_app(router=Router())

        self.assertIn(TELEGRAM_UPDATE_TASK, app.tasks)
        self.assertEqual(app.conf.task_default_queue, TELEGRAM_UPDATE_QUEUE)
        self.assertEqual(app.bot.session.timeout, settings.telegram_request_timeout)


if __name__ == "__main__":
    unittest.main()

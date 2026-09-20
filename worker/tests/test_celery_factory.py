import unittest
from unittest.mock import patch

from aiogram import Router

from shared.config import settings
from worker.celery_factory import CeleryFactory, TELEGRAM_UPDATE_QUEUE, TELEGRAM_UPDATE_TASK


class CeleryFactoryTest(unittest.TestCase):
    def test_producer_does_not_create_telegram_runtime(self):
        app = CeleryFactory.create_app()

        self.assertFalse(hasattr(app, "bot"))
        self.assertFalse(hasattr(app, "dp"))

    def test_worker_registers_shared_task_and_queue(self):
        with patch.object(settings, "telegram_token", "123456:ABCDEF"):
            app = CeleryFactory.create_app(router=Router())

        self.assertIn(TELEGRAM_UPDATE_TASK, app.tasks)
        self.assertEqual(app.conf.task_default_queue, TELEGRAM_UPDATE_QUEUE)
        self.assertEqual(app.bot.session.timeout, settings.telegram_request_timeout)


if __name__ == "__main__":
    unittest.main()

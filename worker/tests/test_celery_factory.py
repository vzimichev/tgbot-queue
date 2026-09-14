import unittest
from unittest.mock import patch

from aiogram import Router

from shared.config import settings
from worker.celery_factory import CeleryFactory


class CeleryFactoryTest(unittest.TestCase):
    def test_producer_does_not_create_telegram_runtime(self):
        app = CeleryFactory.create_app()

        self.assertFalse(hasattr(app, "bot"))
        self.assertFalse(hasattr(app, "dp"))

    def test_worker_registers_only_its_named_task_and_queue(self):
        with patch.object(settings, "telegram_token", "123456:ABCDEF"):
            app = CeleryFactory.create_app(
                router=Router(),
                task_name="sample_bot.process_telegram_update",
                queue_name="sample_bot",
            )

        self.assertIn("sample_bot.process_telegram_update", app.tasks)
        self.assertEqual(app.conf.task_default_queue, "sample_bot")

    def test_worker_requires_explicit_routing(self):
        with self.assertRaises(ValueError):
            CeleryFactory.create_app(router=Router())


if __name__ == "__main__":
    unittest.main()

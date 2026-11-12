import base64
import json
import unittest
from unittest.mock import patch

from bot_factories.admin_bot import lambda_webhook as webhook
from shared.managed_webhook import managed_bot_webhook_secret


class LambdaWebhookTest(unittest.TestCase):
    def setUp(self):
        for name, value in (
            ("webhook_secret_token", "test-secret"),
            ("celery_broker", "sqs"),
            ("sqs_queue_name", "test-updates"),
        ):
            patcher = patch.object(webhook.settings, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = patch.object(webhook.celery_app, "send_task")
        self.send = patcher.start()
        self.addCleanup(patcher.stop)

    def event(self, path="/webhook", secret="test-secret"):
        return {
            "requestContext": {"http": {"method": "POST", "path": path}},
            "headers": {"X-Telegram-Bot-Api-Secret-Token": secret},
            "body": json.dumps({"update_id": 42}),
        }

    def test_admin_publishes_existing_task(self):
        self.assertEqual(webhook.handler(self.event(), None)["statusCode"], 200)
        self.send.assert_called_once_with(
            "telegram.process_update", args=[{"update_id": 42}],
            queue="test-updates", retry=False,
        )

    def test_managed_base64_publishes_bot_id(self):
        event = self.event(
            "/webhook/managed/123", managed_bot_webhook_secret("test-secret", 123)
        )
        event["isBase64Encoded"] = True
        event["body"] = base64.b64encode(event["body"].encode()).decode()
        self.assertEqual(webhook.handler(event, None)["statusCode"], 200)
        self.send.assert_called_once_with(
            "managed_bot.updates", args=[123, {"update_id": 42}],
            queue="test-updates", retry=False,
        )

    def test_invalid_secrets_never_publish(self):
        for path in ("/webhook", "/webhook/managed/123"):
            for secret in (None, "wrong", "неверный"):
                with self.subTest(path=path, secret=secret):
                    self.assertEqual(
                        webhook.handler(self.event(path, secret), None)["statusCode"], 403
                    )
        self.send.assert_not_called()

    def test_invalid_body_never_publishes(self):
        for body in ("{", "[]", "null", '{}', '{"update_id":true}'):
            event = self.event()
            event["body"] = body
            self.assertEqual(webhook.handler(event, None)["statusCode"], 400)
        event["isBase64Encoded"] = True
        event["body"] = "%%%"
        self.assertEqual(webhook.handler(event, None)["statusCode"], 400)
        self.send.assert_not_called()

    def test_publication_failure_returns_retryable_error(self):
        self.send.side_effect = RuntimeError("sensitive details")
        with self.assertLogs(webhook.logger, level="ERROR") as logs:
            result = webhook.handler(self.event(), None)
        self.assertEqual(result["statusCode"], 503)
        self.assertNotIn("sensitive details", " ".join(logs.output))

    def test_malformed_gateway_event_never_publishes(self):
        for event in ({}, {"requestContext": None}, {**self.event(), "body": 42},
                      {**self.event(), "isBase64Encoded": "false"}):
            with self.subTest(event=event):
                self.assertEqual(webhook.handler(event, None)["statusCode"], 400)
        self.send.assert_not_called()

    def test_invalid_telegram_message_never_publishes(self):
        event = self.event()
        event["body"] = json.dumps({"update_id": 42, "message": {"text": "hello"}})
        self.assertEqual(webhook.handler(event, None)["statusCode"], 400)
        self.send.assert_not_called()

    def test_unknown_fields_preserved_without_model_defaults(self):
        event = self.event()
        event["awsMetadata"] = {"future": True}
        update = {"update_id": 42, "future_telegram_field": {"value": 1}}
        event["body"] = json.dumps(update)
        self.assertEqual(webhook.handler(event, None)["statusCode"], 200)
        self.assertEqual(self.send.call_args.kwargs["args"], [update])

    def test_missing_secret_and_redis_fail_closed(self):
        for name, value in (("webhook_secret_token", None), ("celery_broker", "redis")):
            with patch.object(webhook.settings, name, value):
                self.assertEqual(webhook.handler(self.event(), None)["statusCode"], 503)
        self.send.assert_not_called()

    def test_unknown_routes_and_methods_never_publish(self):
        for path in ("/other", "/webhook/managed/0", "/webhook/managed/nope"):
            self.assertEqual(webhook.handler(self.event(path), None)["statusCode"], 404)
        event = self.event()
        event["requestContext"]["http"]["method"] = "GET"
        self.assertEqual(webhook.handler(event, None)["statusCode"], 405)
        self.send.assert_not_called()

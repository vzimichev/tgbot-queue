"""Run the actual inline managed Lambda with AWS clients replaced by mocks."""
import base64
import json
import os
from pathlib import Path
import sys
import textwrap
import types
import unittest
from unittest.mock import Mock, patch

from shared.managed_webhook import managed_bot_webhook_secret


TEMPLATE = Path(__file__).resolve().parents[1] / '8-managed-lambda-stack.yaml'


class ManagedLambdaTests(unittest.TestCase):
    def setUp(self):
        source = TEMPLATE.read_text().split('        ZipFile: |\n', 1)[1].split('\nOutputs:', 1)[0]
        self.sqs = Mock()
        secrets = Mock()
        secrets.get_secret_value.return_value = {'SecretString': 'test-root'}
        boto3 = types.SimpleNamespace(client=lambda name: self.sqs if name == 'sqs' else secrets)
        self.namespace = {}
        with patch.dict(sys.modules, {'boto3': boto3}), patch.dict(os.environ, {
            'SQS_QUEUE_URL': 'managed-queue', 'WEBHOOK_SECRET_ARN': 'secret-arn',
        }):
            exec(compile(textwrap.dedent(source), str(TEMPLATE), 'exec'), self.namespace)
        self.event = {
            'pathParameters': {'bot_id': '123'},
            'headers': {'X-Telegram-Bot-Api-Secret-Token': managed_bot_webhook_secret('test-root', 123)},
            'body': json.dumps({'update_id': 7, 'message': {'text': '/balance'}}),
        }

    def invoke(self):
        return self.namespace['handler'](self.event, None)['statusCode']

    def test_routes_update_with_bot_id(self):
        self.assertEqual(self.invoke(), 200)
        sent = self.sqs.send_message.call_args.kwargs
        self.assertEqual(sent['QueueUrl'], 'managed-queue')
        self.assertEqual(json.loads(sent['MessageBody']), {
            'bot_id': 123, 'update': json.loads(self.event['body']),
        })

    def test_base64_body(self):
        self.event['body'] = base64.b64encode(self.event['body'].encode()).decode()
        self.event['isBase64Encoded'] = True
        self.assertEqual(self.invoke(), 200)

    def test_secret_is_bound_to_bot(self):
        for secret in ('', 'test-root', managed_bot_webhook_secret('test-root', 124)):
            with self.subTest(secret=secret):
                self.event['headers'] = {'x-telegram-bot-api-secret-token': secret}
                self.assertEqual(self.invoke(), 403)
        self.sqs.send_message.assert_not_called()

    def test_empty_root_secret_fails_closed(self):
        self.namespace['WEBHOOK_SECRET'] = b''
        self.event['headers'] = {'x-telegram-bot-api-secret-token': managed_bot_webhook_secret('', 123)}
        self.assertEqual(self.invoke(), 403)
        self.sqs.send_message.assert_not_called()

    def test_invalid_bot_ids(self):
        for bot_id in ('0', '-1', 'abc', '１２３', None):
            with self.subTest(bot_id=bot_id):
                self.event['pathParameters'] = {'bot_id': bot_id}
                self.assertEqual(self.invoke(), 400)
        self.event['pathParameters'] = None
        self.assertEqual(self.invoke(), 400)
        self.sqs.send_message.assert_not_called()

    def test_invalid_updates(self):
        for body in ('bad json', '[]', '{}', '{"update_id": true}', '{"update_id": "7"}'):
            with self.subTest(body=body):
                self.event['body'] = body
                self.assertEqual(self.invoke(), 400)
        self.event.update(body='!!!', isBase64Encoded=True)
        self.assertEqual(self.invoke(), 400)
        self.sqs.send_message.assert_not_called()

    def test_queue_failure_is_retryable(self):
        self.sqs.send_message.side_effect = RuntimeError('unavailable')
        with self.assertLogs(level='ERROR'):
            self.assertEqual(self.invoke(), 503)


if __name__ == '__main__':
    unittest.main()

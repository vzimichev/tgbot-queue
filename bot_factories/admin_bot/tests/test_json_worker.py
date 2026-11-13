import unittest
from unittest.mock import AsyncMock, Mock

from bot_factories.admin_bot.json_worker import consume_once


class JsonWorkerTests(unittest.IsolatedAsyncioTestCase):
    async def test_dispatches_raw_update_before_acknowledging(self):
        sqs = Mock()
        sqs.receive_message.return_value = {
            "Messages": [{"Body": '{"update_id": 42}', "ReceiptHandle": "receipt"}]
        }

        async def dispatch(body):
            self.assertEqual(body, {"update_id": 42})
            sqs.delete_message.assert_not_called()

        await consume_once(sqs, "queue", dispatch)
        sqs.delete_message.assert_called_once_with(
            QueueUrl="queue", ReceiptHandle="receipt"
        )

    async def test_handler_failure_leaves_message_for_retry(self):
        sqs = Mock()
        sqs.receive_message.return_value = {
            "Messages": [{"Body": '{"update_id": 42}', "ReceiptHandle": "receipt"}]
        }
        dispatch = AsyncMock(side_effect=RuntimeError("failed"))
        await consume_once(sqs, "queue", dispatch)
        sqs.delete_message.assert_not_called()

    async def test_invalid_messages_are_not_dispatched_or_deleted(self):
        for body in ('invalid', '[]', '{"update_id": true}', '{"task": "old-task"}'):
            with self.subTest(body=body):
                sqs = Mock()
                sqs.receive_message.return_value = {
                    "Messages": [{"Body": body, "ReceiptHandle": "receipt"}]
                }
                dispatch = AsyncMock()
                await consume_once(sqs, "queue", dispatch)
                dispatch.assert_not_awaited()
                sqs.delete_message.assert_not_called()

    async def test_empty_poll_does_nothing(self):
        sqs = Mock()
        sqs.receive_message.return_value = {}
        dispatch = AsyncMock()
        await consume_once(sqs, "queue", dispatch)
        dispatch.assert_not_awaited()
        sqs.delete_message.assert_not_called()

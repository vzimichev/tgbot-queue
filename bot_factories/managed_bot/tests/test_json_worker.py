import unittest
from unittest.mock import AsyncMock, Mock

from bot_factories.managed_bot.json_worker import consume_once


class JsonWorkerTests(unittest.IsolatedAsyncioTestCase):
    async def test_dispatches_managed_payload_before_acknowledging(self):
        sqs = Mock()
        sqs.receive_message.return_value = {
            "Messages": [{
                "Body": '{"bot_id": 7, "update": {"update_id": 42}}',
                "ReceiptHandle": "receipt",
            }]
        }
        dispatch = AsyncMock(return_value={"status": "ignored"})

        await consume_once(sqs, "queue", dispatch)

        dispatch.assert_awaited_once_with(7, {"update_id": 42})
        sqs.delete_message.assert_called_once_with(
            QueueUrl="queue", ReceiptHandle="receipt"
        )

    async def test_handler_failure_leaves_message_for_retry(self):
        sqs = Mock()
        sqs.receive_message.return_value = {
            "Messages": [{
                "Body": '{"bot_id": 7, "update": {"update_id": 42}}',
                "ReceiptHandle": "receipt",
            }]
        }
        dispatch = AsyncMock(side_effect=RuntimeError("failed"))

        await consume_once(sqs, "queue", dispatch)

        sqs.delete_message.assert_not_called()

    async def test_invalid_messages_are_not_dispatched_or_deleted(self):
        for body in (
            "invalid",
            "[]",
            '{"bot_id": true, "update": {"update_id": 1}}',
            '{"bot_id": 1, "update": {"update_id": true}}',
            '{"update": {"update_id": 1}}',
        ):
            with self.subTest(body=body):
                sqs = Mock()
                sqs.receive_message.return_value = {
                    "Messages": [{"Body": body, "ReceiptHandle": "receipt"}]
                }
                dispatch = AsyncMock()

                await consume_once(sqs, "queue", dispatch)

                dispatch.assert_not_awaited()
                sqs.delete_message.assert_not_called()

import base64
import hashlib
import hmac
import json
import logging
import os

import boto3


logger = logging.getLogger(__name__)
sqs = boto3.client("sqs")

QUEUE_URL = os.environ["SQS_QUEUE_URL"]
WEBHOOK_SECRET = boto3.client("secretsmanager").get_secret_value(
    SecretId=os.environ["WEBHOOK_SECRET_ARN"]
)["SecretString"].encode("utf-8")


def handler(event, context):
    raw_bot_id = (event.get("pathParameters") or {}).get("bot_id", "")
    if not isinstance(raw_bot_id, str) or not raw_bot_id.isascii() or not raw_bot_id.isdecimal():
        return {"statusCode": 400, "body": "Invalid bot ID"}
    bot_id = int(raw_bot_id)
    if bot_id <= 0:
        return {"statusCode": 400, "body": "Invalid bot ID"}

    headers = {
        key.lower(): value
        for key, value in (event.get("headers") or {}).items()
    }
    supplied_secret = headers.get(
        "x-telegram-bot-api-secret-token", ""
    ).encode("utf-8")

    expected_secret = hmac.new(
        WEBHOOK_SECRET, str(bot_id).encode("utf-8"), hashlib.sha256
    ).hexdigest().encode("utf-8")
    if not WEBHOOK_SECRET or not hmac.compare_digest(supplied_secret, expected_secret):
        return {"statusCode": 403, "body": "Forbidden"}

    body = event.get("body") or ""
    try:
        if event.get("isBase64Encoded"):
            body = base64.b64decode(body, validate=True).decode("utf-8")
        update = json.loads(body)
        if not isinstance(update, dict) or type(update.get("update_id")) is not int:
            raise ValueError("Invalid update")
    except (ValueError, TypeError, UnicodeError):
        return {"statusCode": 400, "body": "Invalid update"}

    try:
        sqs.send_message(
            QueueUrl=QUEUE_URL,
            MessageBody=json.dumps({"bot_id": bot_id, "update": update}),
        )
    except Exception:
        logger.exception("Failed to send message to SQS")
        return {"statusCode": 503, "body": "Queue unavailable"}

    return {"statusCode": 200, "body": "OK"}

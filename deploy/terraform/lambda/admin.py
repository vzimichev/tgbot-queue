import base64
import hmac
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
    headers = {
        key.lower(): value
        for key, value in (event.get("headers") or {}).items()
    }
    supplied_secret = headers.get(
        "x-telegram-bot-api-secret-token", ""
    ).encode("utf-8")

    if not hmac.compare_digest(supplied_secret, WEBHOOK_SECRET):
        return {"statusCode": 403, "body": "Forbidden"}

    body = event.get("body") or ""
    if event.get("isBase64Encoded"):
        body = base64.b64decode(body).decode("utf-8")

    try:
        sqs.send_message(
            QueueUrl=QUEUE_URL,
            MessageBody=body,
        )
    except Exception:
        logger.exception("Failed to send message to SQS")
        return {"statusCode": 503, "body": "Queue unavailable"}

    return {"statusCode": 200, "body": "OK"}

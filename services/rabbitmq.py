import json
import logging
from typing import Optional

import pika
from pika.exceptions import AMQPConnectionError, StreamLostError

from core.config import settings

logger = logging.getLogger("rabbitmq")


class RabbitMQClient:
    def __init__(self):
        self.connection = None
        self.channel = None
        self._connect()

    def _connect(self):
        """Create or restore a connection."""
        try:
            logger.info(
                "Connecting to RabbitMQ at %s:%s ...",
                settings.rabbitmq_host,
                settings.rabbitmq_port,
            )

            self.connection = pika.BlockingConnection(
                pika.ConnectionParameters(
                    host=settings.rabbitmq_host,
                    port=settings.rabbitmq_port,
                    credentials=pika.PlainCredentials(
                        settings.rabbitmq_user,
                        settings.rabbitmq_password,
                    ),
                    heartbeat=30,
                    blocked_connection_timeout=30,
                )
            )
            self.channel = self.connection.channel()
            self.channel.queue_declare(queue=settings.rabbitmq_queue, durable=True)

            logger.info(
                "Connected to RabbitMQ and queue declared: %s", settings.rabbitmq_queue
            )

        except AMQPConnectionError as e:
            logger.error("RabbitMQ connection failed: %s", e)
            self.connection = None
            self.channel = None

    def _ensure_connection(self):
        """Reconnect if connection/channel is dead."""
        if (
            not self.connection
            or self.connection.is_closed
            or not self.channel
            or self.channel.is_closed
        ):
            logger.warning("RabbitMQ connection lost. Reconnecting...")
            self._connect()

    def publish(self, message: dict):
        """Publish message, reconnecting on failure."""
        self._ensure_connection()

        if not self.channel:
            logger.error("Cannot publish: RabbitMQ unavailable")
            return

        try:
            self.channel.basic_publish(
                exchange="",
                routing_key=settings.rabbitmq_queue,
                body=json.dumps(message).encode(),
                properties=pika.BasicProperties(delivery_mode=2),
            )
            logger.debug(
                "Published message to RabbitMQ queue '%s'", settings.rabbitmq_queue
            )

        except (AMQPConnectionError, StreamLostError) as e:
            logger.warning("Lost connection while publishing: %s", e)
            logger.info("Attempting reconnection...")
            self._connect()

            if self.channel:
                logger.info("Reconnected. Republishing message...")
                try:
                    self.channel.basic_publish(
                        exchange="",
                        routing_key=settings.rabbitmq_queue,
                        body=json.dumps(message).encode(),
                        properties=pika.BasicProperties(delivery_mode=2),
                    )
                    logger.info("Message successfully republished.")
                except Exception as e2:
                    logger.error("Failed to republish message: %s", e2)
            else:
                logger.error("Reconnection failed. Message lost.")


rabbit = RabbitMQClient()

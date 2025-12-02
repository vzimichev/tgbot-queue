import json

import pika

from app.core.config import settings


class RabbitMQClient:
    def __init__(self):
        self.connection = pika.BlockingConnection(
            pika.ConnectionParameters(
                host=settings.rabbitmq_host,
                port=settings.rabbitmq_port,
                credentials=pika.PlainCredentials(
                    settings.rabbitmq_user, settings.rabbitmq_password
                ),
            )
        )
        self.channel = self.connection.channel()
        self.channel.queue_declare(queue=settings.rabbitmq_queue, durable=True)

    def publish(self, message: dict):
        self.channel.basic_publish(
            exchange="",
            routing_key=settings.rabbitmq_queue,
            body=json.dumps(message).encode(),
            properties=pika.BasicProperties(delivery_mode=2),
        )


rabbit = RabbitMQClient()

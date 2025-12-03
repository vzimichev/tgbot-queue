import json

import pika
from app.config import settings


def callback(ch, method, properties, body):
    print("Got task:", json.loads(body))
    # TODO: do work


def main():
    connection = pika.BlockingConnection(
        pika.ConnectionParameters(
            host=settings.rabbitmq_host,
            credentials=pika.PlainCredentials(
                settings.rabbitmq_user,
                settings.rabbitmq_password,
            ),
        )
    )

    channel = connection.channel()
    channel.queue_declare(queue=settings.rabbitmq_queue, durable=True)

    channel.basic_consume(
        queue=settings.rabbitmq_queue, on_message_callback=callback, auto_ack=True
    )

    print("Worker started")
    channel.start_consuming()


if __name__ == "__main__":
    main()

from faststream.rabbit import RabbitBroker, RabbitExchange, RabbitQueue

from app.core.config import settings
from app.messaging.queues import (
    DLQ_NAME,
    DLX_NAME,
    MAX_ATTEMPTS,
    PAYMENTS_EXCHANGE,
    PAYMENTS_QUEUE,
    RETRY_EXCHANGE,
    retry_delay_ms,
    retry_queue_name,
)

broker = RabbitBroker(settings.rabbitmq_url)

payments_exchange = RabbitExchange(PAYMENTS_EXCHANGE, durable=True)
retry_exchange = RabbitExchange(RETRY_EXCHANGE, durable=True)
dlx_exchange = RabbitExchange(DLX_NAME, durable=True)

payments_queue = RabbitQueue(
    PAYMENTS_QUEUE,
    durable=True,
    routing_key=PAYMENTS_QUEUE,
    arguments={
        "x-dead-letter-exchange": DLX_NAME,
        "x-dead-letter-routing-key": DLQ_NAME,
    },
)
retry_queues = [
    RabbitQueue(
        retry_queue_name(attempt),
        durable=True,
        routing_key=retry_queue_name(attempt),
        arguments={
            "x-message-ttl": retry_delay_ms(attempt),
            "x-dead-letter-exchange": PAYMENTS_EXCHANGE,
            "x-dead-letter-routing-key": PAYMENTS_QUEUE,
        },
    )
    for attempt in range(1, MAX_ATTEMPTS)
]
dlq_queue = RabbitQueue(DLQ_NAME, durable=True, routing_key=DLQ_NAME)


async def declare_topology(broker: RabbitBroker) -> None:
    """Объявляет обменники и очереди.

    Retry-очереди без потребителей: сообщение лежит в них до истечения TTL,
    после чего RabbitMQ возвращает его в payments.new.
    """
    bindings = [
        (payments_exchange, payments_queue),
        *((retry_exchange, queue) for queue in retry_queues),
        (dlx_exchange, dlq_queue),
    ]
    for exchange, queue in bindings:
        declared_exchange = await broker.declare_exchange(exchange)
        declared_queue = await broker.declare_queue(queue)
        await declared_queue.bind(declared_exchange, routing_key=queue.routing_key)

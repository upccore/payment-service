from faststream.rabbit import RabbitBroker, RabbitExchange, RabbitQueue

from app.core.config import settings
from app.messaging.queues import DLQ_NAME, DLX_NAME, PAYMENTS_EXCHANGE, PAYMENTS_QUEUE

broker = RabbitBroker(settings.rabbitmq_url)

payments_exchange = RabbitExchange(PAYMENTS_EXCHANGE, durable=True)
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
dlq_queue = RabbitQueue(DLQ_NAME, durable=True, routing_key=DLQ_NAME)


async def declare_topology() -> None:
    for exchange, queue in (
        (payments_exchange, payments_queue),
        (dlx_exchange, dlq_queue),
    ):
        declared_exchange = await broker.declare_exchange(exchange)
        declared_queue = await broker.declare_queue(queue)
        await declared_queue.bind(declared_exchange, routing_key=queue.routing_key)

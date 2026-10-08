import asyncio
import time
from collections.abc import AsyncIterator, Iterator

import pytest
from aio_pika.abc import AbstractIncomingMessage, AbstractRobustQueue
from faststream.rabbit import RabbitBroker
from testcontainers.community.rabbitmq import RabbitMqContainer

from app.messaging.broker import (
    declare_topology,
    dlq_queue,
    payments_queue,
    retry_exchange,
    retry_queues,
)
from app.messaging.queues import retry_delay_ms, retry_queue_name


@pytest.fixture(scope="session")
def rabbitmq_url() -> Iterator[str]:
    with RabbitMqContainer("rabbitmq:3.13-alpine") as rabbitmq:
        host = rabbitmq.get_container_host_ip()
        port = rabbitmq.get_exposed_port(rabbitmq.port)
        yield f"amqp://guest:guest@{host}:{port}/"


@pytest.fixture
async def rabbit(rabbitmq_url: str) -> AsyncIterator[RabbitBroker]:
    broker = RabbitBroker(rabbitmq_url)
    await broker.connect()
    await declare_topology(broker)
    for queue in (payments_queue, dlq_queue, *retry_queues):
        await (await broker.declare_queue(queue)).purge()
    yield broker
    await broker.stop()


async def wait_for_message(
    queue: AbstractRobustQueue, seconds: float
) -> AbstractIncomingMessage:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        message = await queue.get(fail=False)
        if message is not None:
            return message
        await asyncio.sleep(0.05)
    raise AssertionError(f"No message in {queue.name} within {seconds} s")


@pytest.mark.parametrize("attempt", [1, 2])
async def test_retry_queue_returns_message_after_delay(
    rabbit: RabbitBroker, attempt: int
) -> None:
    payments = await rabbit.declare_queue(payments_queue)
    started = time.monotonic()

    await rabbit.publish(
        {"payment_id": "1"},
        exchange=retry_exchange,
        routing_key=retry_queue_name(attempt),
        headers={"x-attempt": attempt + 1},
    )
    message = await wait_for_message(
        payments, seconds=retry_delay_ms(attempt) / 1000 + 3
    )
    await message.ack()

    assert time.monotonic() - started >= retry_delay_ms(attempt) / 1000 * 0.9
    assert message.headers["x-attempt"] == attempt + 1


async def test_rejected_message_goes_to_dlq(rabbit: RabbitBroker) -> None:
    payments = await rabbit.declare_queue(payments_queue)
    dlq = await rabbit.declare_queue(dlq_queue)
    await rabbit.publish(
        {"payment_id": "1"},
        exchange="payments",
        routing_key=payments_queue.routing_key,
        message_id="message-1",
    )

    await (await wait_for_message(payments, seconds=3)).reject(requeue=False)
    dead = await wait_for_message(dlq, seconds=3)
    await dead.ack()

    assert dead.message_id == "message-1"

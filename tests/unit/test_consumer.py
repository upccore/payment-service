import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
from faststream.rabbit import RabbitBroker, TestRabbitBroker

from app.messaging import consumer
from app.messaging.broker import broker, payments_exchange, payments_queue
from app.messaging.queues import ATTEMPT_HEADER
from app.messaging.schemas import PaymentEvent


class RecordingHandler:
    def __init__(self) -> None:
        self.calls: list[tuple[PaymentEvent, str, int]] = []

    async def handle(self, event: PaymentEvent, message_id: str, attempt: int) -> None:
        self.calls.append((event, message_id, attempt))


@pytest.fixture
async def test_broker() -> AsyncIterator[RabbitBroker]:
    async with TestRabbitBroker(broker) as test_broker:
        yield test_broker


@pytest.fixture
def handler() -> RecordingHandler:
    handler = RecordingHandler()
    consumer.app.context.set_global("payment_handler", handler)
    return handler


async def publish(test_broker: RabbitBroker, **kwargs: Any) -> uuid.UUID:
    payment_id = uuid.uuid4()
    await test_broker.publish(
        {"payment_id": str(payment_id)},
        exchange=payments_exchange,
        routing_key=payments_queue.routing_key,
        message_id="message-1",
        **kwargs,
    )
    return payment_id


async def test_first_delivery_is_attempt_one(
    test_broker: RabbitBroker, handler: RecordingHandler
) -> None:
    payment_id = await publish(test_broker)

    assert handler.calls == [(PaymentEvent(payment_id=payment_id), "message-1", 1)]


async def test_attempt_is_read_from_header(
    test_broker: RabbitBroker, handler: RecordingHandler
) -> None:
    await publish(test_broker, headers={ATTEMPT_HEADER: 3})

    assert [attempt for _, _, attempt in handler.calls] == [3]

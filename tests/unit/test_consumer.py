import uuid
from collections.abc import AsyncIterator
from uuid import UUID

import pytest
from faststream.rabbit import TestRabbitBroker

from app.messaging import consumer
from app.messaging.broker import broker, payments_exchange, payments_queue


class FlakyProcessor:
    def __init__(self, failures: int) -> None:
        self.failures = failures
        self.calls: list[UUID] = []

    async def process(self, payment_id: UUID) -> None:
        self.calls.append(payment_id)
        if len(self.calls) <= self.failures:
            raise RuntimeError("processing failed")


@pytest.fixture(autouse=True)
def no_retry_delay(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(consumer, "RETRY_BASE_DELAY", 0)


@pytest.fixture
async def test_broker() -> AsyncIterator[TestRabbitBroker]:
    async with TestRabbitBroker(broker) as test_broker:
        yield test_broker


async def publish(test_broker: TestRabbitBroker, processor: FlakyProcessor) -> UUID:
    consumer.app.context.set_global("processor", processor)
    payment_id = uuid.uuid4()
    await test_broker.publish(
        {"payment_id": str(payment_id)},
        exchange=payments_exchange,
        routing_key=payments_queue.routing_key,
    )
    return payment_id


async def test_message_is_processed_once_on_success(
    test_broker: TestRabbitBroker,
) -> None:
    processor = FlakyProcessor(failures=0)

    payment_id = await publish(test_broker, processor)

    assert processor.calls == [payment_id]


async def test_processing_is_retried_until_success(
    test_broker: TestRabbitBroker,
) -> None:
    processor = FlakyProcessor(failures=2)

    payment_id = await publish(test_broker, processor)

    assert processor.calls == [payment_id] * 3


async def test_message_is_rejected_after_max_attempts(
    test_broker: TestRabbitBroker,
) -> None:
    processor = FlakyProcessor(failures=consumer.MAX_ATTEMPTS)

    with pytest.raises(RuntimeError, match="processing failed"):
        await publish(test_broker, processor)

    assert len(processor.calls) == consumer.MAX_ATTEMPTS

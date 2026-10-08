import uuid
from uuid import UUID

import pytest
from faststream.rabbit import RabbitExchange

from app.domain.exceptions import PaymentNotFoundError
from app.messaging.queues import ATTEMPT_HEADER, MAX_ATTEMPTS
from app.messaging.retry import PaymentEventHandler
from app.messaging.schemas import PaymentEvent
from tests.unit.fakes import FakePublisher

RETRY_EXCHANGE = RabbitExchange("payments.retry")


class FlakyProcessor:
    def __init__(self, fails: bool, error: Exception | None = None) -> None:
        self.fails = fails
        self.error = error or RuntimeError("processing failed")
        self.calls: list[UUID] = []

    async def process(self, payment_id: UUID) -> None:
        self.calls.append(payment_id)
        if self.fails:
            raise self.error


def make_handler(fails: bool) -> tuple[PaymentEventHandler, FakePublisher]:
    publisher = FakePublisher()
    handler = PaymentEventHandler(FlakyProcessor(fails), publisher, RETRY_EXCHANGE)
    return handler, publisher


async def test_successful_attempt_is_not_retried() -> None:
    handler, publisher = make_handler(fails=False)

    await handler.handle(PaymentEvent(payment_id=uuid.uuid4()), "message-1", 1)

    assert publisher.published == []


@pytest.mark.parametrize(
    ("attempt", "routing_key"),
    [(1, "payments.retry.1000ms"), (2, "payments.retry.2000ms")],
)
async def test_failed_attempt_is_sent_to_retry_queue(
    attempt: int, routing_key: str
) -> None:
    handler, publisher = make_handler(fails=True)
    event = PaymentEvent(payment_id=uuid.uuid4())

    await handler.handle(event, "message-1", attempt)

    assert publisher.published == [
        {
            "message": {"payment_id": str(event.payment_id)},
            "exchange": RETRY_EXCHANGE,
            "routing_key": routing_key,
            "persist": True,
            "message_id": "message-1",
            "headers": {ATTEMPT_HEADER: attempt + 1},
        }
    ]


async def test_last_failed_attempt_raises_without_retry() -> None:
    handler, publisher = make_handler(fails=True)

    with pytest.raises(RuntimeError, match="processing failed"):
        await handler.handle(
            PaymentEvent(payment_id=uuid.uuid4()), "message-1", MAX_ATTEMPTS
        )

    assert publisher.published == []


async def test_permanent_error_goes_to_dlq_on_first_attempt() -> None:
    publisher = FakePublisher()
    payment_id = uuid.uuid4()
    processor = FlakyProcessor(fails=True, error=PaymentNotFoundError(payment_id))
    handler = PaymentEventHandler(processor, publisher, RETRY_EXCHANGE)

    with pytest.raises(PaymentNotFoundError):
        await handler.handle(PaymentEvent(payment_id=payment_id), "message-1", 1)

    assert publisher.published == []

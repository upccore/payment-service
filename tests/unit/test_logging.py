import logging
import uuid
from uuid import UUID

from faststream.rabbit import RabbitExchange

from app.core.logging import HealthCheckFilter, PaymentContextFilter, payment_id_var
from app.messaging.retry import PaymentEventHandler
from app.messaging.schemas import PaymentEvent
from tests.unit.fakes import FakePublisher


def make_record(message: str = "message") -> logging.LogRecord:
    return logging.LogRecord("test", logging.INFO, __file__, 1, message, None, None)


def test_filter_adds_current_payment_id() -> None:
    token = payment_id_var.set("payment-1")
    try:
        record = make_record()
        PaymentContextFilter().filter(record)
    finally:
        payment_id_var.reset(token)

    assert record.__dict__["payment_id"] == "payment-1"


def test_filter_uses_placeholder_outside_payment_context() -> None:
    record = make_record()

    PaymentContextFilter().filter(record)

    assert record.__dict__["payment_id"] == "-"


class ContextRecordingProcessor:
    def __init__(self) -> None:
        self.seen: list[str] = []

    async def process(self, payment_id: UUID) -> None:
        self.seen.append(payment_id_var.get())


async def test_handler_sets_payment_id_while_processing() -> None:
    processor = ContextRecordingProcessor()
    handler = PaymentEventHandler(
        processor, FakePublisher(), RabbitExchange("payments.retry")
    )
    event = PaymentEvent(payment_id=uuid.uuid4())

    await handler.handle(event, "message-1", 1)

    assert processor.seen == [str(event.payment_id)]
    assert payment_id_var.get() == "-"


def test_health_check_requests_are_filtered() -> None:
    health = make_record('"GET /health HTTP/1.1" 200')
    payments = make_record('"GET /api/v1/payments/1 HTTP/1.1" 200')

    assert not HealthCheckFilter().filter(health)
    assert HealthCheckFilter().filter(payments)

import uuid
from datetime import datetime, timezone

import pytest

from app.domain.exceptions import PaymentNotFoundError
from app.domain.payments import PaymentStatus
from app.services.processing import PaymentProcessor
from tests.factories import make_payment
from tests.unit.fakes import FakeGateway, FakeUnitOfWork, FakeWebhookSender


def make_processor(
    uow: FakeUnitOfWork, gateway: FakeGateway, webhooks: FakeWebhookSender
) -> PaymentProcessor:
    return PaymentProcessor(uow, gateway, webhooks)


@pytest.mark.parametrize("result", [PaymentStatus.succeeded, PaymentStatus.failed])
async def test_pending_payment_is_charged_saved_and_notified(
    result: PaymentStatus,
) -> None:
    uow, gateway, webhooks = FakeUnitOfWork(), FakeGateway(result), FakeWebhookSender()
    payment = make_payment()
    uow.payments.items[payment.id] = payment

    await make_processor(uow, gateway, webhooks).process(payment.id)

    assert payment.status == result
    assert payment.processed_at is not None
    assert gateway.calls == 1
    assert uow.commits == 1
    assert webhooks.sent == [payment]


async def test_processed_payment_is_not_charged_again() -> None:
    uow, gateway, webhooks = FakeUnitOfWork(), FakeGateway(), FakeWebhookSender()
    processed_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    payment = make_payment(status=PaymentStatus.succeeded, processed_at=processed_at)
    uow.payments.items[payment.id] = payment

    await make_processor(uow, gateway, webhooks).process(payment.id)

    assert gateway.calls == 0
    assert uow.commits == 0
    assert payment.processed_at == processed_at
    assert webhooks.sent == [payment]


async def test_webhook_error_propagates_after_result_is_saved() -> None:
    uow, gateway = FakeUnitOfWork(), FakeGateway()
    webhooks = FakeWebhookSender(error=RuntimeError("webhook is down"))
    payment = make_payment()
    uow.payments.items[payment.id] = payment

    with pytest.raises(RuntimeError, match="webhook is down"):
        await make_processor(uow, gateway, webhooks).process(payment.id)

    assert payment.status == PaymentStatus.succeeded
    assert uow.commits == 1


async def test_missing_payment_raises() -> None:
    uow, gateway, webhooks = FakeUnitOfWork(), FakeGateway(), FakeWebhookSender()

    with pytest.raises(PaymentNotFoundError):
        await make_processor(uow, gateway, webhooks).process(uuid.uuid4())

    assert gateway.calls == 0
    assert webhooks.sent == []

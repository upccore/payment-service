import asyncio
from functools import partial

import pytest

from app.db.unit_of_work import UnitOfWork
from app.domain.payments import PaymentStatus
from app.services.payments import PaymentService
from app.services.processing import PaymentProcessor
from tests.factories import make_new_payment
from tests.unit.fakes import FakeGateway, FakeWebhookSender


async def test_result_is_saved(
    uow_factory: partial[UnitOfWork], payment_service: PaymentService
) -> None:
    payment = await payment_service.create(make_new_payment())
    webhooks = FakeWebhookSender()
    processor = PaymentProcessor(
        uow_factory, FakeGateway(PaymentStatus.failed), webhooks, gateway_timeout=1
    )

    await processor.process(payment.id)

    saved = await payment_service.get(payment.id)
    assert saved.status == PaymentStatus.failed
    assert saved.processed_at is not None
    assert [p.id for p in webhooks.sent] == [payment.id]


async def test_concurrent_processing_charges_once(
    uow_factory: partial[UnitOfWork], payment_service: PaymentService
) -> None:
    payment = await payment_service.create(make_new_payment())
    gateway, webhooks = FakeGateway(delay=0.2), FakeWebhookSender()
    processor = PaymentProcessor(uow_factory, gateway, webhooks, gateway_timeout=1)

    await asyncio.gather(processor.process(payment.id), processor.process(payment.id))

    assert gateway.calls == 1
    assert len(webhooks.sent) == 2
    assert (await payment_service.get(payment.id)).status == PaymentStatus.succeeded


async def test_gateway_timeout_releases_payment_lock(
    uow_factory: partial[UnitOfWork], payment_service: PaymentService
) -> None:
    payment = await payment_service.create(make_new_payment())
    webhooks = FakeWebhookSender()
    hanging = PaymentProcessor(
        uow_factory, FakeGateway(delay=10), webhooks, gateway_timeout=0.1
    )
    working = PaymentProcessor(
        uow_factory, FakeGateway(), webhooks, gateway_timeout=0.1
    )

    with pytest.raises(TimeoutError):
        await hanging.process(payment.id)
    assert (await payment_service.get(payment.id)).status == PaymentStatus.pending

    await asyncio.wait_for(working.process(payment.id), timeout=1)
    assert (await payment_service.get(payment.id)).status == PaymentStatus.succeeded

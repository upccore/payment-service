import asyncio
from functools import partial

from app.db.models import Payment
from app.db.unit_of_work import UnitOfWork
from app.domain.payments import PaymentStatus
from app.services.payments import PaymentService
from app.services.processing import PaymentProcessor
from tests.factories import make_new_payment
from tests.unit.fakes import FakeGateway, FakeWebhookSender


class SlowGateway(FakeGateway):
    async def charge(self, payment: Payment) -> PaymentStatus:
        await asyncio.sleep(0.2)
        return await super().charge(payment)


async def test_result_is_saved(
    uow_factory: partial[UnitOfWork], payment_service: PaymentService
) -> None:
    payment = await payment_service.create(make_new_payment())
    webhooks = FakeWebhookSender()
    processor = PaymentProcessor(
        uow_factory, FakeGateway(PaymentStatus.failed), webhooks
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
    gateway, webhooks = SlowGateway(), FakeWebhookSender()
    processor = PaymentProcessor(uow_factory, gateway, webhooks)

    await asyncio.gather(processor.process(payment.id), processor.process(payment.id))

    assert gateway.calls == 1
    assert len(webhooks.sent) == 2
    assert (await payment_service.get(payment.id)).status == PaymentStatus.succeeded

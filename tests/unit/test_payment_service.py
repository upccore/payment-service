import uuid

import pytest

from app.domain.exceptions import PaymentNotFoundError
from app.domain.payments import PaymentStatus
from app.messaging.queues import PAYMENTS_QUEUE
from app.services.payments import PaymentService
from tests.factories import make_new_payment, make_payment
from tests.unit.fakes import FakeUnitOfWork


@pytest.fixture
def uow() -> FakeUnitOfWork:
    return FakeUnitOfWork()


@pytest.fixture
def service(uow: FakeUnitOfWork) -> PaymentService:
    return PaymentService(uow)


async def test_create_saves_pending_payment_and_outbox_event(
    service: PaymentService, uow: FakeUnitOfWork
) -> None:
    data = make_new_payment()

    payment = await service.create(data)

    assert payment.status == PaymentStatus.pending
    assert payment.amount == data.amount
    assert payment.idempotency_key == data.idempotency_key
    assert uow.payments.items == {payment.id: payment}
    assert uow.outbox.events == [(PAYMENTS_QUEUE, {"payment_id": str(payment.id)})]
    assert uow.commits == 1


async def test_create_returns_existing_payment_for_same_key(
    service: PaymentService, uow: FakeUnitOfWork
) -> None:
    existing = make_payment()
    uow.payments.items[existing.id] = existing

    payment = await service.create(
        make_new_payment(idempotency_key=existing.idempotency_key)
    )

    assert payment is existing
    assert uow.outbox.events == []
    assert uow.commits == 0


async def test_create_returns_existing_payment_when_insert_conflicts(
    service: PaymentService, uow: FakeUnitOfWork
) -> None:
    existing = make_payment()
    uow.payments.items[existing.id] = existing
    uow.payments.missed_lookups = 1

    payment = await service.create(
        make_new_payment(idempotency_key=existing.idempotency_key)
    )

    assert payment is existing
    assert len(uow.payments.items) == 1
    assert uow.outbox.events == []
    assert uow.commits == 0


async def test_get_returns_payment(
    service: PaymentService, uow: FakeUnitOfWork
) -> None:
    payment = make_payment()
    uow.payments.items[payment.id] = payment

    assert await service.get(payment.id) is payment


async def test_get_raises_when_payment_missing(service: PaymentService) -> None:
    with pytest.raises(PaymentNotFoundError):
        await service.get(uuid.uuid4())

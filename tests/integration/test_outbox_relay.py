from functools import partial
from typing import Any

import pytest
from faststream.rabbit import RabbitExchange
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Outbox
from app.db.unit_of_work import UnitOfWork
from app.messaging.queues import PAYMENTS_QUEUE
from app.messaging.outbox_relay import OutboxRelay
from app.services.payments import PaymentService
from tests.factories import make_new_payment

EXCHANGE = RabbitExchange("payments")


class FakeBroker:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.published: list[dict[str, Any]] = []

    async def publish(self, message: Any, **kwargs: Any) -> None:
        if self.error:
            raise self.error
        self.published.append({"message": message, **kwargs})


async def published_at(
    session_factory: async_sessionmaker[AsyncSession],
) -> list[Any]:
    async with session_factory() as session:
        return list(await session.scalars(select(Outbox.published_at)))


async def test_relay_publishes_pending_events_once(
    uow_factory: partial[UnitOfWork],
    payment_service: PaymentService,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    payments = [await payment_service.create(make_new_payment()) for _ in range(2)]
    broker = FakeBroker()
    relay = OutboxRelay(uow_factory, broker, EXCHANGE)

    await relay.publish_pending()
    await relay.publish_pending()

    assert [p["message"] for p in broker.published] == [
        {"payment_id": str(p.id)} for p in payments
    ]
    assert {p["routing_key"] for p in broker.published} == {PAYMENTS_QUEUE}
    assert {p["exchange"] for p in broker.published} == {EXCHANGE}
    assert all(p["persist"] for p in broker.published)
    assert all(value is not None for value in await published_at(session_factory))


async def test_events_stay_unpublished_when_broker_fails(
    uow_factory: partial[UnitOfWork],
    payment_service: PaymentService,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await payment_service.create(make_new_payment())
    relay = OutboxRelay(
        uow_factory, FakeBroker(ConnectionError("broker is down")), EXCHANGE
    )

    with pytest.raises(ConnectionError):
        await relay.publish_pending()

    assert await published_at(session_factory) == [None]

    broker = FakeBroker()
    await OutboxRelay(uow_factory, broker, EXCHANGE).publish_pending()
    assert len(broker.published) == 1

import asyncio
import logging
from collections.abc import Callable

from faststream.rabbit import RabbitBroker, RabbitExchange

from app.db.unit_of_work import UnitOfWork

logger = logging.getLogger(__name__)

BATCH_SIZE = 100
POLL_INTERVAL = 1


class OutboxRelay:
    """Публикует события из outbox в RabbitMQ.

    Отметка о публикации фиксируется после отправки, поэтому при сбое
    между ними событие уйдёт повторно. Consumer к этому готов.
    """

    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        broker: RabbitBroker,
        exchange: RabbitExchange,
    ) -> None:
        self._uow_factory = uow_factory
        self._broker = broker
        self._exchange = exchange

    async def publish_pending(self) -> None:
        async with self._uow_factory() as uow:
            for event in await uow.outbox.lock_unpublished(BATCH_SIZE):
                await self._broker.publish(
                    event.payload,
                    exchange=self._exchange,
                    routing_key=event.queue,
                    persist=True,
                    message_id=str(event.id),
                )
                uow.outbox.mark_published(event)
            await uow.commit()

    async def run(self) -> None:
        while True:
            try:
                await self.publish_pending()
            except Exception:
                logger.exception("Outbox publishing failed")
            await asyncio.sleep(POLL_INTERVAL)

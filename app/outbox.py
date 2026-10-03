import asyncio
import logging

from sqlalchemy import func, select

from app.broker import broker, payments_exchange
from app.db import async_session
from app.models import Outbox

logger = logging.getLogger(__name__)

BATCH_SIZE = 100
POLL_INTERVAL = 1


async def publish_pending():
    async with async_session() as session, session.begin():
        events = await session.scalars(
            select(Outbox)
            .where(Outbox.published_at.is_(None))
            .order_by(Outbox.created_at)
            .limit(BATCH_SIZE)
            .with_for_update(skip_locked=True)
        )
        for event in events:
            await broker.publish(
                event.payload,
                exchange=payments_exchange,
                routing_key=event.queue,
                persist=True,
                message_id=str(event.id),
            )
            event.published_at = func.now()


async def run_outbox():
    while True:
        try:
            await publish_pending()
        except Exception:
            logger.exception("Outbox publishing failed")
        await asyncio.sleep(POLL_INTERVAL)

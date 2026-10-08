from collections.abc import Sequence
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Outbox


class OutboxRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(self, queue: str, payload: dict[str, Any]) -> None:
        self._session.add(Outbox(queue=queue, payload=payload))

    async def lock_unpublished(self, limit: int) -> Sequence[Outbox]:
        """Блокирует неопубликованные события, пропуская уже занятые."""
        result = await self._session.scalars(
            select(Outbox)
            .where(Outbox.published_at.is_(None))
            .order_by(Outbox.created_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        return result.all()

    @staticmethod
    def mark_published(event: Outbox) -> None:
        event.published_at = func.now()

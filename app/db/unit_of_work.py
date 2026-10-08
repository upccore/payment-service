from types import TracebackType
from typing import Self

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.repositories.outbox import OutboxRepository
from app.repositories.payments import PaymentRepository


class UnitOfWork:
    """Транзакция и репозитории, которые в ней работают.

    Всё, что не зафиксировано через commit, откатывается при выходе из блока.
    """

    payments: PaymentRepository
    outbox: OutboxRepository

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def __aenter__(self) -> Self:
        self._session = self._session_factory()
        self.payments = PaymentRepository(self._session)
        self.outbox = OutboxRepository(self._session)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self._session.close()

    async def commit(self) -> None:
        await self._session.commit()

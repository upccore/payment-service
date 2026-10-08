from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Payment


class PaymentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, payment_id: UUID) -> Payment | None:
        return await self._session.get(Payment, payment_id)

    async def get_for_update(self, payment_id: UUID) -> Payment | None:
        return await self._session.get(Payment, payment_id, with_for_update=True)

    async def get_by_idempotency_key(self, key: str) -> Payment | None:
        return await self._session.scalar(
            select(Payment).where(Payment.idempotency_key == key)
        )

    async def add_if_absent(self, payment: Payment) -> bool:
        """Добавляет платёж, если его idempotency key ещё не занят.

        Вставка идёт в savepoint: при конфликте уникального индекса
        откатывается только она, и транзакцию можно продолжать.
        """
        try:
            async with self._session.begin_nested():
                self._session.add(payment)
        except IntegrityError:
            return False
        return True

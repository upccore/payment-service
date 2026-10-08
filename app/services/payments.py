import uuid
from collections.abc import Callable

from app.db.models import Payment
from app.db.unit_of_work import UnitOfWork
from app.domain.exceptions import PaymentNotFoundError
from app.domain.payments import NewPayment, PaymentStatus
from app.messaging.queues import PAYMENTS_QUEUE


class PaymentService:
    def __init__(self, uow_factory: Callable[[], UnitOfWork]) -> None:
        self._uow_factory = uow_factory

    async def create(self, data: NewPayment) -> Payment:
        """Создаёт платёж и событие для очереди в одной транзакции.

        Если платёж с таким idempotency key уже есть, возвращает его.
        """
        async with self._uow_factory() as uow:
            existing = await uow.payments.get_by_idempotency_key(data.idempotency_key)
            if existing:
                return existing

            payment = Payment(
                id=uuid.uuid4(),
                amount=data.amount,
                currency=data.currency,
                description=data.description,
                payment_metadata=data.metadata,
                idempotency_key=data.idempotency_key,
                webhook_url=data.webhook_url,
                status=PaymentStatus.pending,
            )
            if not await uow.payments.add_if_absent(payment):
                existing = await uow.payments.get_by_idempotency_key(
                    data.idempotency_key
                )
                if existing is None:
                    raise RuntimeError("Payment insert failed without a duplicate")
                return existing

            uow.outbox.add(PAYMENTS_QUEUE, {"payment_id": str(payment.id)})
            await uow.commit()
            return payment

    async def get(self, payment_id: uuid.UUID) -> Payment:
        async with self._uow_factory() as uow:
            payment = await uow.payments.get(payment_id)
            if payment is None:
                raise PaymentNotFoundError(payment_id)
            return payment

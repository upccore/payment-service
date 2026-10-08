from collections.abc import Callable
from datetime import datetime, timezone
from uuid import UUID

from app.db.unit_of_work import UnitOfWork
from app.domain.exceptions import PaymentNotFoundError
from app.domain.payments import PaymentStatus
from app.services.gateway import PaymentGateway
from app.services.webhooks import WebhookSender


class PaymentProcessor:
    """Проводит платёж через шлюз и уведомляет клиента.

    Если результат уже сохранён, шлюз повторно не вызывается:
    при повторной обработке отправляется только webhook.
    """

    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        gateway: PaymentGateway,
        webhooks: WebhookSender,
    ) -> None:
        self._uow_factory = uow_factory
        self._gateway = gateway
        self._webhooks = webhooks

    async def process(self, payment_id: UUID) -> None:
        async with self._uow_factory() as uow:
            payment = await uow.payments.get_for_update(payment_id)
            if payment is None:
                raise PaymentNotFoundError(payment_id)
            if payment.status == PaymentStatus.pending:
                payment.status = await self._gateway.charge(payment)
                payment.processed_at = datetime.now(timezone.utc)
                await uow.commit()
        await self._webhooks.send(payment)

import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

from app.db.unit_of_work import UnitOfWork
from app.domain.exceptions import PaymentNotFoundError
from app.domain.payments import PaymentStatus
from app.services.protocols import Gateway, WebhookNotifier

logger = logging.getLogger(__name__)


class PaymentProcessor:
    """Проводит платёж через шлюз и уведомляет клиента.

    Строка платежа блокируется на время вызова шлюза, поэтому параллельная
    обработка одного платежа не приведёт к двойному списанию. Если результат
    уже сохранён, шлюз повторно не вызывается: отправляется только webhook.
    Вызов шлюза ограничен gateway_timeout, чтобы зависший шлюз не держал
    блокировку и соединение с базой.
    """

    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        gateway: Gateway,
        webhooks: WebhookNotifier,
        gateway_timeout: float,
    ) -> None:
        self._uow_factory = uow_factory
        self._gateway = gateway
        self._webhooks = webhooks
        self._gateway_timeout = gateway_timeout

    async def process(self, payment_id: UUID) -> None:
        async with self._uow_factory() as uow:
            payment = await uow.payments.get_for_update(payment_id)
            if payment is None:
                raise PaymentNotFoundError(payment_id)
            if payment.status == PaymentStatus.pending:
                async with asyncio.timeout(self._gateway_timeout):
                    payment.status = await self._gateway.charge(payment)
                payment.processed_at = datetime.now(UTC)
                await uow.commit()
                logger.info("Payment processed with status %s", payment.status)
            else:
                logger.info("Payment already %s, sending webhook only", payment.status)
        await self._webhooks.send(payment)

import logging

from faststream.rabbit import RabbitExchange

from app.core.logging import payment_id_var
from app.domain.exceptions import PermanentError
from app.messaging.protocols import MessagePublisher, Processor
from app.messaging.queues import (
    ATTEMPT_HEADER,
    MAX_ATTEMPTS,
    retry_delay_ms,
    retry_queue_name,
)
from app.messaging.schemas import PaymentEvent

logger = logging.getLogger(__name__)


class PaymentEventHandler:
    """Обрабатывает событие платежа и решает, что делать при ошибке.

    После неудачной попытки событие уходит в retry-очередь с нужной задержкой,
    а исходное сообщение подтверждается. После последней попытки или при
    PermanentError исключение пробрасывается, брокер отклоняет сообщение,
    и оно попадает в DLQ.
    """

    def __init__(
        self,
        processor: Processor,
        publisher: MessagePublisher,
        retry_exchange: RabbitExchange,
    ) -> None:
        self._processor = processor
        self._publisher = publisher
        self._retry_exchange = retry_exchange

    async def handle(self, event: PaymentEvent, message_id: str, attempt: int) -> None:
        token = payment_id_var.set(str(event.payment_id))
        try:
            await self._handle(event, message_id, attempt)
        finally:
            payment_id_var.reset(token)

    async def _handle(self, event: PaymentEvent, message_id: str, attempt: int) -> None:
        try:
            await self._processor.process(event.payment_id)
        except PermanentError as error:
            logger.error("Permanent error, moving to DLQ without retry: %s", error)
            raise
        except Exception as error:
            if attempt >= MAX_ATTEMPTS:
                logger.error(
                    "Attempt %s/%s failed, moving to DLQ: %s",
                    attempt,
                    MAX_ATTEMPTS,
                    error,
                )
                raise
            logger.warning(
                "Attempt %s/%s failed, retry in %s ms: %s",
                attempt,
                MAX_ATTEMPTS,
                retry_delay_ms(attempt),
                error,
            )
            await self._publisher.publish(
                event.model_dump(mode="json"),
                exchange=self._retry_exchange,
                routing_key=retry_queue_name(attempt),
                persist=True,
                message_id=message_id,
                headers={ATTEMPT_HEADER: attempt + 1},
            )

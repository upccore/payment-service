import logging

from faststream.rabbit import RabbitExchange

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
    а исходное сообщение подтверждается. После последней попытки исключение
    пробрасывается, брокер отклоняет сообщение, и оно попадает в DLQ.
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
        try:
            await self._processor.process(event.payment_id)
        except Exception as error:
            if attempt >= MAX_ATTEMPTS:
                logger.error(
                    "Payment %s: attempt %s/%s failed, moving to DLQ: %s",
                    event.payment_id,
                    attempt,
                    MAX_ATTEMPTS,
                    error,
                )
                raise
            logger.warning(
                "Payment %s: attempt %s/%s failed, retry in %s ms: %s",
                event.payment_id,
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

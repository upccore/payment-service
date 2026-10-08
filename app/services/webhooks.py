import logging
from datetime import datetime
from decimal import Decimal
from uuid import UUID

import httpx
from pydantic import BaseModel, ConfigDict, Field

from app.db.models import Payment
from app.domain.exceptions import WebhookRejectedError
from app.domain.payments import Currency, PaymentStatus

logger = logging.getLogger(__name__)

RETRYABLE_CLIENT_ERRORS = {408, 429}


class PaymentWebhook(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    payment_id: UUID = Field(validation_alias="id")
    status: PaymentStatus
    amount: Decimal
    currency: Currency
    processed_at: datetime


class WebhookSender:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def send(self, payment: Payment) -> None:
        """Отправляет результат платежа клиенту. Ответ не 2xx считается ошибкой.

        Ответ 4xx, кроме 408 и 429, означает, что клиент не примет webhook
        и при повторе: такая ошибка не повторяется.
        """
        payload = PaymentWebhook.model_validate(payment).model_dump(mode="json")
        response = await self._client.post(payment.webhook_url, json=payload)
        if (
            response.is_client_error
            and response.status_code not in RETRYABLE_CLIENT_ERRORS
        ):
            raise WebhookRejectedError(payment.webhook_url, response.status_code)
        response.raise_for_status()
        logger.info("Webhook delivered to %s", payment.webhook_url)

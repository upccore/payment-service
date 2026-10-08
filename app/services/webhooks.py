from datetime import datetime
from decimal import Decimal
from uuid import UUID

import httpx
from pydantic import BaseModel, ConfigDict, Field

from app.db.models import Payment
from app.domain.payments import Currency, PaymentStatus


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
        """Отправляет результат платежа клиенту. Ответ не 2xx считается ошибкой."""
        payload = PaymentWebhook.model_validate(payment).model_dump(mode="json")
        response = await self._client.post(payment.webhook_url, json=payload)
        response.raise_for_status()

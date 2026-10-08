from typing import Protocol

from app.db.models import Payment
from app.domain.payments import PaymentStatus


class Gateway(Protocol):
    async def charge(self, payment: Payment) -> PaymentStatus: ...


class WebhookNotifier(Protocol):
    async def send(self, payment: Payment) -> None: ...

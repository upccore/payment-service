import asyncio
import random

from app.db.models import Payment
from app.domain.payments import PaymentStatus


class PaymentGateway:
    """Эмуляция внешнего платёжного шлюза."""

    def __init__(
        self,
        min_delay: float = 2,
        max_delay: float = 5,
        success_rate: float = 0.9,
    ) -> None:
        self._min_delay = min_delay
        self._max_delay = max_delay
        self._success_rate = success_rate

    async def charge(self, payment: Payment) -> PaymentStatus:
        await asyncio.sleep(random.uniform(self._min_delay, self._max_delay))
        if random.random() < self._success_rate:
            return PaymentStatus.succeeded
        return PaymentStatus.failed

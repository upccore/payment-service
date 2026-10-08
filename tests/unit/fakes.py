from types import TracebackType
from typing import Any, Self
from uuid import UUID

from app.db.models import Payment
from app.domain.payments import PaymentStatus


class FakePaymentRepository:
    def __init__(self) -> None:
        self.items: dict[UUID, Payment] = {}
        self.missed_lookups = 0

    async def get(self, payment_id: UUID) -> Payment | None:
        return self.items.get(payment_id)

    async def get_for_update(self, payment_id: UUID) -> Payment | None:
        return self.items.get(payment_id)

    async def get_by_idempotency_key(self, key: str) -> Payment | None:
        """Первые missed_lookups поисков ничего не находят: так эмулируется гонка."""
        if self.missed_lookups:
            self.missed_lookups -= 1
            return None
        return next((p for p in self.items.values() if p.idempotency_key == key), None)

    async def add_if_absent(self, payment: Payment) -> bool:
        if any(
            p.idempotency_key == payment.idempotency_key for p in self.items.values()
        ):
            return False
        self.items[payment.id] = payment
        return True


class FakeOutboxRepository:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []

    def add(self, queue: str, payload: dict[str, Any]) -> None:
        self.events.append((queue, payload))


class FakeUnitOfWork:
    def __init__(self) -> None:
        self.payments = FakePaymentRepository()
        self.outbox = FakeOutboxRepository()
        self.commits = 0

    def __call__(self) -> Self:
        return self

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        pass

    async def commit(self) -> None:
        self.commits += 1


class FakeGateway:
    def __init__(self, status: PaymentStatus = PaymentStatus.succeeded) -> None:
        self.status = status
        self.calls = 0

    async def charge(self, payment: Payment) -> PaymentStatus:
        self.calls += 1
        return self.status


class FakeWebhookSender:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.sent: list[Payment] = []

    async def send(self, payment: Payment) -> None:
        self.sent.append(payment)
        if self.error:
            raise self.error

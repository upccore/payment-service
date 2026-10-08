import uuid
from decimal import Decimal
from typing import Any

from app.db.models import Payment
from app.domain.payments import Currency, NewPayment, PaymentStatus


def make_new_payment(**overrides: Any) -> NewPayment:
    data: dict[str, Any] = {
        "amount": Decimal("100.50"),
        "currency": Currency.RUB,
        "description": "Order 1",
        "metadata": {"order_id": 1},
        "webhook_url": "https://example.com/webhook",
        "idempotency_key": f"key-{uuid.uuid4()}",
    }
    return NewPayment(**(data | overrides))


def make_payment(**overrides: Any) -> Payment:
    data: dict[str, Any] = {
        "id": uuid.uuid4(),
        "amount": Decimal("100.50"),
        "currency": Currency.RUB,
        "description": "Order 1",
        "payment_metadata": {"order_id": 1},
        "status": PaymentStatus.pending,
        "idempotency_key": f"key-{uuid.uuid4()}",
        "webhook_url": "https://example.com/webhook",
    }
    return Payment(**(data | overrides))

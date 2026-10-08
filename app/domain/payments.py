import enum
from dataclasses import dataclass
from decimal import Decimal
from typing import Any


class Currency(enum.StrEnum):
    RUB = "RUB"
    USD = "USD"
    EUR = "EUR"


class PaymentStatus(enum.StrEnum):
    pending = "pending"
    succeeded = "succeeded"
    failed = "failed"


@dataclass(frozen=True)
class NewPayment:
    """Данные для создания платежа."""

    amount: Decimal
    currency: Currency
    description: str
    metadata: dict[str, Any]
    webhook_url: str
    idempotency_key: str

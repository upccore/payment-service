from uuid import UUID


class PermanentError(Exception):
    """Ошибка, которую повторная попытка не исправит."""


class PaymentNotFoundError(PermanentError):
    def __init__(self, payment_id: UUID) -> None:
        super().__init__(f"Payment {payment_id} not found")
        self.payment_id = payment_id


class IdempotencyConflictError(Exception):
    def __init__(self, idempotency_key: str) -> None:
        super().__init__(
            f"Idempotency key {idempotency_key!r} is already used "
            "with different request parameters"
        )
        self.idempotency_key = idempotency_key


class WebhookRejectedError(PermanentError):
    def __init__(self, url: str, status_code: int) -> None:
        super().__init__(f"Webhook {url} rejected with status {status_code}")
        self.url = url
        self.status_code = status_code

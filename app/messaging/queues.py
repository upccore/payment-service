PAYMENTS_EXCHANGE = "payments"
PAYMENTS_QUEUE = "payments.new"
RETRY_EXCHANGE = "payments.retry"
DLX_NAME = "payments.dlx"
DLQ_NAME = "payments.dlq"

ATTEMPT_HEADER = "x-attempt"
MAX_ATTEMPTS = 3
RETRY_BASE_DELAY_MS = 1000


def retry_delay_ms(attempt: int) -> int:
    """Задержка после неудачной попытки attempt: 1 с, 2 с, 4 с…"""
    return int(RETRY_BASE_DELAY_MS * 2 ** (attempt - 1))


def retry_queue_name(attempt: int) -> str:
    return f"payments.retry.{retry_delay_ms(attempt)}ms"

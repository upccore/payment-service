import logging
from contextvars import ContextVar

payment_id_var: ContextVar[str] = ContextVar("payment_id", default="-")

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s [payment=%(payment_id)s] %(message)s"


class PaymentContextFilter(logging.Filter):
    """Добавляет в запись лога payment_id платежа, который сейчас обрабатывается."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.payment_id = payment_id_var.get()
        return True


class HealthCheckFilter(logging.Filter):
    """Убирает из access-лога uvicorn запросы healthcheck."""

    def filter(self, record: logging.LogRecord) -> bool:
        return "/health" not in record.getMessage()


def setup_logging(level: str) -> None:
    handler = logging.StreamHandler()
    handler.addFilter(PaymentContextFilter())
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    logging.getLogger("uvicorn.access").addFilter(HealthCheckFilter())

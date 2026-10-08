import asyncio
from functools import partial

import httpx
from faststream import AckPolicy, Context, FastStream, Logger
from faststream.rabbit import Channel

from app.db.session import session_factory
from app.db.unit_of_work import UnitOfWork
from app.messaging.broker import (
    broker,
    declare_topology,
    payments_exchange,
    payments_queue,
)
from app.messaging.schemas import PaymentEvent
from app.services.gateway import PaymentGateway
from app.services.processing import PaymentProcessor
from app.services.webhooks import WebhookSender

PREFETCH_COUNT = 10
MAX_ATTEMPTS = 3
RETRY_BASE_DELAY = 1
WEBHOOK_TIMEOUT = 10

app = FastStream(broker)


@app.on_startup
async def create_processor() -> None:
    http_client = httpx.AsyncClient(timeout=WEBHOOK_TIMEOUT)
    app.context.set_global("http_client", http_client)
    app.context.set_global(
        "processor",
        PaymentProcessor(
            uow_factory=partial(UnitOfWork, session_factory),
            gateway=PaymentGateway(),
            webhooks=WebhookSender(http_client),
        ),
    )


@app.after_startup
async def setup() -> None:
    await declare_topology()


@app.after_shutdown
async def close_http_client(http_client: httpx.AsyncClient = Context()) -> None:
    await http_client.aclose()


@broker.subscriber(
    payments_queue,
    payments_exchange,
    channel=Channel(prefetch_count=PREFETCH_COUNT),
    ack_policy=AckPolicy.REJECT_ON_ERROR,
)
async def handle_payment(
    event: PaymentEvent,
    logger: Logger,
    processor: PaymentProcessor = Context(),
) -> None:
    """Обрабатывает платёж до MAX_ATTEMPTS раз, после чего сообщение уходит в DLQ."""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            await processor.process(event.payment_id)
            return
        except Exception as error:
            logger.warning(
                "Payment %s: attempt %s/%s failed: %s",
                event.payment_id,
                attempt,
                MAX_ATTEMPTS,
                error,
            )
            if attempt == MAX_ATTEMPTS:
                raise
            await asyncio.sleep(RETRY_BASE_DELAY * 2 ** (attempt - 1))

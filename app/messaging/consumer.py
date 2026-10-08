from functools import partial

import httpx
from faststream import AckPolicy, Context, FastStream
from faststream.rabbit import Channel, RabbitMessage

from app.core.config import settings
from app.core.logging import setup_logging
from app.db.session import engine, session_factory
from app.db.unit_of_work import UnitOfWork
from app.messaging.broker import (
    broker,
    declare_topology,
    payments_exchange,
    payments_queue,
    retry_exchange,
)
from app.messaging.queues import ATTEMPT_HEADER
from app.messaging.retry import PaymentEventHandler
from app.messaging.schemas import PaymentEvent
from app.services.gateway import PaymentGateway
from app.services.processing import PaymentProcessor
from app.services.webhooks import WebhookSender

app = FastStream(broker)


@app.on_startup
async def create_handler() -> None:
    setup_logging(settings.log_level)
    http_client = httpx.AsyncClient(timeout=settings.webhook_timeout)
    processor = PaymentProcessor(
        uow_factory=partial(UnitOfWork, session_factory),
        gateway=PaymentGateway(),
        webhooks=WebhookSender(http_client),
        gateway_timeout=settings.gateway_timeout,
    )
    app.context.set_global("http_client", http_client)
    app.context.set_global(
        "payment_handler", PaymentEventHandler(processor, broker, retry_exchange)
    )


@app.after_startup
async def setup() -> None:
    await declare_topology(broker)


@app.after_shutdown
async def close_resources(http_client: httpx.AsyncClient = Context()) -> None:
    await http_client.aclose()
    await engine.dispose()


@broker.subscriber(
    payments_queue,
    payments_exchange,
    channel=Channel(prefetch_count=settings.consumer_prefetch),
    ack_policy=AckPolicy.REJECT_ON_ERROR,
)
async def handle_payment(
    event: PaymentEvent,
    message: RabbitMessage,
    payment_handler: PaymentEventHandler = Context(),
) -> None:
    attempt = int(message.headers.get(ATTEMPT_HEADER, 1))
    await payment_handler.handle(event, message.message_id, attempt)

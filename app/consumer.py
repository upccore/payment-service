import asyncio
import random
from datetime import datetime, timezone
from uuid import UUID

import httpx
from faststream import AckPolicy, FastStream, Logger
from faststream.rabbit import Channel

from app.broker import broker, declare_topology, payments_exchange, payments_queue
from app.db import async_session
from app.models import Payment, PaymentStatus
from app.schemas import PaymentEvent, PaymentWebhook

PREFETCH_COUNT = 10
MAX_ATTEMPTS = 3
RETRY_BASE_DELAY = 1
WEBHOOK_TIMEOUT = 10

app = FastStream(broker)


@app.after_startup
async def setup() -> None:
    await declare_topology()


async def emulate_gateway(payment: Payment) -> None:
    await asyncio.sleep(random.uniform(2, 5))
    succeeded = random.random() < 0.9
    payment.status = PaymentStatus.succeeded if succeeded else PaymentStatus.failed
    payment.processed_at = datetime.now(timezone.utc)


async def send_webhook(payment: Payment) -> None:
    payload = PaymentWebhook.model_validate(payment).model_dump(mode="json")
    async with httpx.AsyncClient(timeout=WEBHOOK_TIMEOUT) as client:
        response = await client.post(payment.webhook_url, json=payload)
        response.raise_for_status()


async def process_payment(payment_id: UUID) -> None:
    async with async_session() as session:
        payment = await session.get_one(Payment, payment_id, with_for_update=True)
        if payment.status == PaymentStatus.pending:
            await emulate_gateway(payment)
            await session.commit()
    await send_webhook(payment)


@broker.subscriber(
    payments_queue,
    payments_exchange,
    channel=Channel(prefetch_count=PREFETCH_COUNT),
    ack_policy=AckPolicy.REJECT_ON_ERROR,
)
async def handle_payment(event: PaymentEvent, logger: Logger) -> None:
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            await process_payment(event.payment_id)
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

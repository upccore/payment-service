import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import partial

from fastapi import FastAPI

from app.api.errors import register_error_handlers
from app.api.routes.payments import router as payments_router
from app.db.session import session_factory
from app.db.unit_of_work import UnitOfWork
from app.messaging.broker import broker, declare_topology, payments_exchange
from app.messaging.outbox_relay import OutboxRelay


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    await broker.connect()
    await declare_topology()
    relay = OutboxRelay(partial(UnitOfWork, session_factory), broker, payments_exchange)
    relay_task = asyncio.create_task(relay.run())
    yield
    relay_task.cancel()
    await broker.stop()


app = FastAPI(title="Payment Service", lifespan=lifespan)
app.include_router(payments_router)
register_error_handlers(app)

import asyncio
from contextlib import suppress
from functools import partial

from faststream import Context, FastStream

from app.core.config import settings
from app.core.logging import setup_logging
from app.db.session import engine, session_factory
from app.db.unit_of_work import UnitOfWork
from app.messaging.broker import broker, declare_topology, payments_exchange
from app.messaging.outbox_relay import OutboxRelay

app = FastStream(broker)


@app.on_startup
async def configure_logging() -> None:
    setup_logging(settings.log_level)


@app.after_startup
async def start_relay() -> None:
    await declare_topology(broker)
    relay = OutboxRelay(partial(UnitOfWork, session_factory), broker, payments_exchange)
    app.context.set_global("relay_task", asyncio.create_task(relay.run()))


@app.on_shutdown
async def stop_relay(relay_task: asyncio.Task[None] = Context()) -> None:
    relay_task.cancel()
    with suppress(asyncio.CancelledError):
        await relay_task
    await engine.dispose()

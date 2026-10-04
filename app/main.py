import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import router
from app.broker import broker, declare_topology
from app.outbox import run_outbox


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    await broker.connect()
    await declare_topology()
    outbox_task = asyncio.create_task(run_outbox())
    yield
    outbox_task.cancel()
    await broker.stop()


app = FastAPI(title="Payment Service", lifespan=lifespan)
app.include_router(router)

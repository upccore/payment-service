from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.errors import register_error_handlers
from app.api.routes.health import router as health_router
from app.api.routes.payments import router as payments_router
from app.core.config import settings
from app.core.logging import setup_logging
from app.db.session import engine


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    setup_logging(settings.log_level)
    yield
    await engine.dispose()


app = FastAPI(title="Payment Service", lifespan=lifespan)
app.include_router(payments_router)
app.include_router(health_router)
register_error_handlers(app)

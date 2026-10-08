from functools import partial

from fastapi import Header, HTTPException, status

from app.core.config import settings
from app.db.session import session_factory
from app.db.unit_of_work import UnitOfWork
from app.services.payments import PaymentService


async def verify_api_key(x_api_key: str | None = Header(default=None)) -> None:
    if x_api_key != settings.api_key:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid API key")


def get_payment_service() -> PaymentService:
    return PaymentService(partial(UnitOfWork, session_factory))

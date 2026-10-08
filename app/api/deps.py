from functools import partial

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import settings
from app.db.session import session_factory
from app.db.unit_of_work import UnitOfWork
from app.services.payments import PaymentService


async def verify_api_key(x_api_key: str | None = Header(default=None)) -> None:
    if x_api_key != settings.api_key:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid API key")


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    return session_factory


def get_payment_service(
    factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory),
) -> PaymentService:
    return PaymentService(partial(UnitOfWork, factory))

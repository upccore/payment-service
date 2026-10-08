import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.deps import get_session_factory
from app.db.session import ping_database

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/health")
async def health(
    factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory),
) -> dict[str, str]:
    try:
        await ping_database(factory)
    except Exception as error:
        logger.warning("Health check failed: %s", error)
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Database is unavailable"
        ) from error
    return {"status": "ok"}

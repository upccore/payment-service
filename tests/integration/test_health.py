from collections.abc import AsyncIterator

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.deps import get_session_factory
from app.main import app


@pytest.fixture
async def unreachable_database() -> AsyncIterator[None]:
    engine = create_async_engine(
        "postgresql+asyncpg://user:password@127.0.0.1:1/db",
        connect_args={"timeout": 1},
    )
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(engine)
    app.dependency_overrides[get_session_factory] = lambda: factory
    yield
    await engine.dispose()


async def test_health_is_ok_without_api_key(client: AsyncClient) -> None:
    del client.headers["X-API-Key"]

    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_health_reports_unavailable_database(
    client: AsyncClient, unreachable_database: None
) -> None:
    response = await client.get("/health")

    assert response.status_code == 503

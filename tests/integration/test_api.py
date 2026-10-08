import asyncio
import uuid
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Outbox, Payment
from app.messaging.queues import PAYMENTS_QUEUE

URL = "/api/v1/payments"


def payment_body(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "amount": "100.50",
        "currency": "RUB",
        "description": "Order 1",
        "metadata": {"order_id": 1},
        "webhook_url": "https://example.com/webhook",
    }
    return body | overrides


async def create(client: AsyncClient, key: str, **overrides: Any) -> Any:
    return await client.post(
        URL, json=payment_body(**overrides), headers={"Idempotency-Key": key}
    )


async def count(session_factory: async_sessionmaker[AsyncSession], model: type) -> int:
    async with session_factory() as session:
        return await session.scalar(select(func.count()).select_from(model)) or 0


async def test_create_payment(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    response = await create(client, "order-1")

    assert response.status_code == 202
    body = response.json()
    assert set(body) == {"payment_id", "status", "created_at"}
    assert body["status"] == "pending"

    async with session_factory() as session:
        events = (await session.scalars(select(Outbox))).all()
    assert [(e.queue, e.payload, e.published_at) for e in events] == [
        (PAYMENTS_QUEUE, {"payment_id": body["payment_id"]}, None)
    ]


async def test_get_payment(client: AsyncClient) -> None:
    payment_id = (await create(client, "order-1")).json()["payment_id"]

    response = await client.get(f"{URL}/{payment_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["payment_id"] == payment_id
    assert body["amount"] == "100.50"
    assert body["currency"] == "RUB"
    assert body["metadata"] == {"order_id": 1}
    assert body["status"] == "pending"
    assert body["idempotency_key"] == "order-1"
    assert body["processed_at"] is None


async def test_same_idempotency_key_returns_same_payment(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    first = await create(client, "order-1")
    second = await create(client, "order-1")

    assert second.status_code == 202
    assert second.json() == first.json()
    assert await count(session_factory, Payment) == 1
    assert await count(session_factory, Outbox) == 1


async def test_equivalent_body_with_same_key_returns_same_payment(
    client: AsyncClient,
) -> None:
    first = await create(client, "order-1", metadata={"a": 1, "b": 2})
    second = await create(client, "order-1", amount="100.5", metadata={"b": 2, "a": 1})

    assert second.status_code == 202
    assert second.json()["payment_id"] == first.json()["payment_id"]


async def test_different_body_with_same_key_returns_409(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await create(client, "order-1")

    response = await create(client, "order-1", amount="200.00")

    assert response.status_code == 409
    assert "order-1" in response.json()["detail"]
    assert await count(session_factory, Payment) == 1
    assert await count(session_factory, Outbox) == 1


async def test_concurrent_requests_with_same_key_create_one_payment(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    responses = await asyncio.gather(*(create(client, "order-1") for _ in range(10)))

    assert {r.status_code for r in responses} == {202}
    assert len({r.json()["payment_id"] for r in responses}) == 1
    assert await count(session_factory, Payment) == 1
    assert await count(session_factory, Outbox) == 1


async def test_get_missing_payment_returns_404(client: AsyncClient) -> None:
    response = await client.get(f"{URL}/{uuid.uuid4()}")

    assert response.status_code == 404


@pytest.mark.parametrize("headers", [{"X-API-Key": "wrong"}, {"X-API-Key": ""}])
async def test_invalid_api_key_returns_401(
    client: AsyncClient, headers: dict[str, str]
) -> None:
    get_response = await client.get(f"{URL}/{uuid.uuid4()}", headers=headers)
    post_response = await client.post(
        URL, json=payment_body(), headers=headers | {"Idempotency-Key": "order-1"}
    )

    assert get_response.status_code == 401
    assert post_response.status_code == 401


async def test_missing_api_key_returns_401(client: AsyncClient) -> None:
    del client.headers["X-API-Key"]

    response = await client.get(f"{URL}/{uuid.uuid4()}")

    assert response.status_code == 401


@pytest.mark.parametrize("headers", [{}, {"Idempotency-Key": ""}])
async def test_missing_idempotency_key_returns_422(
    client: AsyncClient, headers: dict[str, str]
) -> None:
    response = await client.post(URL, json=payment_body(), headers=headers)

    assert response.status_code == 422


@pytest.mark.parametrize(
    "overrides",
    [
        {"amount": "0"},
        {"amount": "-1"},
        {"amount": "1.001"},
        {"currency": "GBP"},
        {"webhook_url": "not-a-url"},
    ],
)
async def test_invalid_body_returns_422(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    overrides: dict[str, Any],
) -> None:
    response = await create(client, "order-1", **overrides)

    assert response.status_code == 422
    assert await count(session_factory, Payment) == 0

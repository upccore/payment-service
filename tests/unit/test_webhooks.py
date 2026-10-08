import json
from datetime import UTC, datetime

import httpx
import pytest

from app.domain.payments import PaymentStatus
from app.services.webhooks import WebhookSender
from tests.factories import make_payment


async def test_send_posts_payment_result() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200)

    payment = make_payment(
        status=PaymentStatus.succeeded,
        processed_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await WebhookSender(client).send(payment)

    assert len(requests) == 1
    assert requests[0].method == "POST"
    assert str(requests[0].url) == payment.webhook_url
    assert json.loads(requests[0].content) == {
        "payment_id": str(payment.id),
        "status": "succeeded",
        "amount": "100.50",
        "currency": "RUB",
        "processed_at": "2026-01-01T00:00:00Z",
    }


async def test_send_raises_on_error_response() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(500))
    payment = make_payment(
        status=PaymentStatus.failed,
        processed_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(httpx.HTTPStatusError):
            await WebhookSender(client).send(payment)

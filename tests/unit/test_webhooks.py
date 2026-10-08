import json
from datetime import UTC, datetime

import httpx
import pytest

from app.domain.exceptions import WebhookRejectedError
from app.domain.payments import PaymentStatus
from app.services.webhooks import WebhookSender
from tests.factories import make_payment

PROCESSED_AT = datetime(2026, 1, 1, tzinfo=UTC)


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


@pytest.mark.parametrize("status_code", [400, 404, 410, 422])
async def test_client_error_is_permanent(status_code: int) -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(status_code))
    payment = make_payment(status=PaymentStatus.failed, processed_at=PROCESSED_AT)

    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(WebhookRejectedError) as error:
            await WebhookSender(client).send(payment)

    assert error.value.status_code == status_code


@pytest.mark.parametrize("status_code", [408, 429, 500, 503])
async def test_temporary_error_is_retryable(status_code: int) -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(status_code))
    payment = make_payment(status=PaymentStatus.failed, processed_at=PROCESSED_AT)

    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(httpx.HTTPStatusError):
            await WebhookSender(client).send(payment)

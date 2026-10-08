import pytest

from app.domain.payments import PaymentStatus
from app.services.gateway import PaymentGateway
from tests.factories import make_payment


@pytest.mark.parametrize(
    ("success_rate", "expected"),
    [(1, PaymentStatus.succeeded), (0, PaymentStatus.failed)],
)
async def test_charge_result_follows_success_rate(
    success_rate: float, expected: PaymentStatus
) -> None:
    gateway = PaymentGateway(min_delay=0, max_delay=0, success_rate=success_rate)

    assert await gateway.charge(make_payment()) == expected

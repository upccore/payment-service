from uuid import UUID

from fastapi import APIRouter, Depends, Header, status

from app.api.deps import get_payment_service, verify_api_key
from app.api.schemas import PaymentAccepted, PaymentCreate, PaymentDetail
from app.db.models import Payment
from app.domain.payments import NewPayment
from app.services.payments import PaymentService

router = APIRouter(prefix="/api/v1/payments", dependencies=[Depends(verify_api_key)])


@router.post("", status_code=status.HTTP_202_ACCEPTED, response_model=PaymentAccepted)
async def create_payment(
    data: PaymentCreate,
    idempotency_key: str = Header(min_length=1),
    service: PaymentService = Depends(get_payment_service),
) -> Payment:
    return await service.create(
        NewPayment(
            amount=data.amount,
            currency=data.currency,
            description=data.description,
            metadata=data.metadata,
            webhook_url=str(data.webhook_url),
            idempotency_key=idempotency_key,
        )
    )


@router.get("/{payment_id}", response_model=PaymentDetail)
async def get_payment(
    payment_id: UUID, service: PaymentService = Depends(get_payment_service)
) -> Payment:
    return await service.get(payment_id)

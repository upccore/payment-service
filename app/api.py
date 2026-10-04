import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import PAYMENTS_QUEUE, settings
from app.db import get_session
from app.models import Outbox, Payment
from app.schemas import PaymentAccepted, PaymentCreate, PaymentDetail


async def verify_api_key(x_api_key: str | None = Header(default=None)):
    if x_api_key != settings.api_key:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid API key")


router = APIRouter(prefix="/api/v1/payments", dependencies=[Depends(verify_api_key)])


async def get_by_idempotency_key(session: AsyncSession, key: str) -> Payment | None:
    return await session.scalar(select(Payment).where(Payment.idempotency_key == key))


@router.post("", status_code=status.HTTP_202_ACCEPTED, response_model=PaymentAccepted)
async def create_payment(
    data: PaymentCreate,
    idempotency_key: str = Header(),
    session: AsyncSession = Depends(get_session),
):
    existing = await get_by_idempotency_key(session, idempotency_key)
    if existing:
        return existing

    payment = Payment(
        id=uuid.uuid4(),
        amount=data.amount,
        currency=data.currency,
        description=data.description,
        payment_metadata=data.metadata,
        idempotency_key=idempotency_key,
        webhook_url=str(data.webhook_url),
    )
    session.add(payment)
    session.add(Outbox(queue=PAYMENTS_QUEUE, payload={"payment_id": str(payment.id)}))
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        return await get_by_idempotency_key(session, idempotency_key)
    return payment


@router.get("/{payment_id}", response_model=PaymentDetail)
async def get_payment(
    payment_id: uuid.UUID, session: AsyncSession = Depends(get_session)
):
    payment = await session.get(Payment, payment_id)
    if not payment:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment not found")
    return payment

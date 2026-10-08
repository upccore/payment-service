from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.domain.exceptions import PaymentNotFoundError


async def payment_not_found_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND, content={"detail": str(exc)}
    )


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(PaymentNotFoundError, payment_not_found_handler)

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.domain.exceptions import IdempotencyConflictError, PaymentNotFoundError

ERROR_STATUSES: dict[type[Exception], int] = {
    PaymentNotFoundError: status.HTTP_404_NOT_FOUND,
    IdempotencyConflictError: status.HTTP_409_CONFLICT,
}


async def domain_error_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=ERROR_STATUSES[type(exc)], content={"detail": str(exc)}
    )


def register_error_handlers(app: FastAPI) -> None:
    for error in ERROR_STATUSES:
        app.add_exception_handler(error, domain_error_handler)

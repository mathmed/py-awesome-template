from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.domain.errors.domain_errors import (
    ConflictError,
    DomainError,
    NotFoundError,
    ServiceUnavailableError,
)

STATUS_BY_ERROR: tuple[tuple[type[DomainError], int], ...] = (
    (NotFoundError, status.HTTP_404_NOT_FOUND),
    (ConflictError, status.HTTP_409_CONFLICT),
    (ServiceUnavailableError, status.HTTP_503_SERVICE_UNAVAILABLE),
)


async def domain_error_handler(_: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, DomainError):
        raise TypeError(f"the domain error handler got a {type(exc).__name__}")
    status_code = next(
        (code for error, code in STATUS_BY_ERROR if isinstance(exc, error)),
        status.HTTP_400_BAD_REQUEST,
    )
    return JSONResponse(status_code=status_code, content={"detail": exc.message})


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(DomainError, domain_error_handler)

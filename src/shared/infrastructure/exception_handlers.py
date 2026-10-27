from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from shared.domain.errors import (
    ConflictError,
    InvalidInputError,
    NotFoundError,
    ServiceUnavailableError,
)


async def _not_found_handler(_request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(exc)})


async def _conflict_handler(_request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": str(exc)})


async def _invalid_input_handler(_request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": str(exc)})


async def _service_unavailable_handler(_request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": str(exc)})


def register_exception_handlers(application: FastAPI) -> None:
    application.add_exception_handler(NotFoundError, _not_found_handler)
    application.add_exception_handler(ConflictError, _conflict_handler)
    application.add_exception_handler(InvalidInputError, _invalid_input_handler)
    application.add_exception_handler(ServiceUnavailableError, _service_unavailable_handler)

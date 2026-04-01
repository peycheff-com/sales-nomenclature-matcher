from __future__ import annotations

import logging

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DataError, IntegrityError

logger = logging.getLogger(__name__)


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(IntegrityError)
    async def sqlalchemy_integrity_error_handler(request: Request, exc: IntegrityError):
        logger.warning(f"IntegrityError on {request.method} {request.url}: {exc}")

        detail = "Data integrity conflict."
        # Attempt to parse standard postgres unique constraint string
        if exc.orig and hasattr(exc.orig, "diag") and exc.orig.diag.message_detail:
            detail = exc.orig.diag.message_detail

        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "error": "Conflict",
                "detail": detail,
            },
        )

    @app.exception_handler(DataError)
    async def sqlalchemy_data_error_handler(request: Request, exc: DataError):
        logger.warning(f"DataError on {request.method} {request.url}: {exc}")
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "error": "Unprocessable Entity",
                "detail": "Database cannot process the provided data type or format.",
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": "Internal Server Error",
                "detail": "An unexpected error occurred.",
            },
        )

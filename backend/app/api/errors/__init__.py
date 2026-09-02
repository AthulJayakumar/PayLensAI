"""Structured API error contracts and handlers."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class APIError(Exception):
    """Expected API failure with a safe status, code, message, and details."""

    def __init__(
        self,
        *,
        status_code: int,
        code: str,
        message: str,
        details: list[Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or []


def error_payload(code: str, message: str, details: list[Any] | None = None) -> dict:
    """Build the consistent error envelope returned by every API route."""

    return {"error": {"code": code, "message": message, "details": details or []}}


def install_error_handlers(app: FastAPI) -> None:
    """Register safe handlers for business and request-validation errors."""

    @app.exception_handler(APIError)
    async def api_error_handler(request: Request, error: APIError) -> JSONResponse:
        return JSONResponse(
            status_code=error.status_code,
            content=error_payload(error.code, error.message, error.details),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, error: RequestValidationError
    ) -> JSONResponse:
        details = [
            {
                "location": ".".join(str(item) for item in detail["loc"]),
                "message": detail["msg"],
                "type": detail["type"],
            }
            for detail in error.errors()
        ]
        return JSONResponse(
            status_code=422,
            content=error_payload("REQUEST_VALIDATION_ERROR", "The request is invalid.", details),
        )

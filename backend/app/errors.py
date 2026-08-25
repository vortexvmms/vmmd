"""Consistent API error envelopes without breaking the existing `detail` field."""
from __future__ import annotations

import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(HTTPException)
    async def http_error(_request: Request, exc: HTTPException):
        message = str(exc.detail)
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": message, "error": {"code": f"HTTP_{exc.status_code}", "message": message}},
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={
                "detail": "Check the highlighted information and try again.",
                "error": {"code": "VALIDATION_ERROR", "message": "Invalid request", "fields": exc.errors()},
            },
        )

    @app.exception_handler(Exception)
    async def unexpected_error(_request: Request, _exc: Exception):
        reference = uuid.uuid4().hex[:10]
        return JSONResponse(
            status_code=500,
            content={
                "detail": f"Something went wrong. Try again. Reference: {reference}",
                "error": {"code": "INTERNAL_ERROR", "message": "Unexpected server error", "reference": reference},
            },
        )

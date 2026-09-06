from __future__ import annotations

import logging
import traceback

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

log = logging.getLogger("locan.errors")


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


class QuotaExceeded(ApiError):
    def __init__(self, scope: str):
        super().__init__(
            429,
            "quota_exceeded",
            "You've reached today's free limit for this tool. Please try again tomorrow.",
        )
        self.scope = scope


async def _notify(request: Request, kind: str, title: str, fields: dict) -> None:
    notifier = getattr(request.app.state, "notifier", None)
    if notifier is not None:
        await notifier.event(kind, title, fields, request)


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(request: Request, exc: ApiError) -> JSONResponse:
        if isinstance(exc, QuotaExceeded):
            await _notify(request, "quota", f"{exc.scope} limit hit", {"scope": exc.scope})
        elif exc.status >= 500:
            await _notify(
                request, "error", f"{exc.code} on {request.url.path}", {"status": exc.status, "code": exc.code, "message": exc.message}
            )
        return JSONResponse(status_code=exc.status, content={"error": exc.message, "code": exc.code})

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        first = exc.errors()[0] if exc.errors() else {}
        loc = ".".join(str(p) for p in first.get("loc", []) if p != "body")
        msg = first.get("msg", "Invalid request")
        return JSONResponse(
            status_code=422,
            content={"error": f"{loc}: {msg}" if loc else msg, "code": "validation_error"},
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:  # pragma: no cover
        log.exception("unhandled error on %s", request.url.path)
        tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))[-1500:]
        await _notify(request, "error", f"{type(exc).__name__} on {request.url.path}", {"exception": repr(exc), "traceback": tb})
        return JSONResponse(status_code=500, content={"error": "Something went wrong. Please try again.", "code": "internal_error"})

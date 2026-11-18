"""Application errors and handlers: consistent JSON, never a stack trace to the client."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


class AppError(Exception):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code, self.code, self.message = status_code, code, message


def _body(request: Request, code: str, message: str, details: list[dict[str, str]] | None = None) -> dict:
    error: dict = {"code": code, "message": message, "request_id": getattr(request.state, "request_id", None)}
    if details:
        error["details"] = details
    return {"error": error}


def _friendly(field: str, err_type: str, msg: str, ctx: dict) -> str:
    if err_type == "json_invalid":
        return "Request body must be valid JSON."
    if err_type == "missing":
        return f"'{field}' is required."
    if field == "message":
        if err_type == "string_too_short":
            return "Message must not be empty."
        if err_type == "string_too_long":
            return f"Message is too long (maximum {ctx.get('max_length')} characters)."
        if err_type in {"string_type", "string_unicode"}:
            return "Message must be text."
    if field == "user_id":
        if err_type == "string_pattern_mismatch":
            return "user_id must look like 'usr_123' (letters, digits, '_' or '-' after 'usr_')."
        if err_type in {"string_type", "string_unicode"}:
            return "user_id must be text."
    if err_type == "extra_forbidden":
        return f"Unexpected field '{field}'."
    return msg


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=_body(request, exc.code, exc.message))

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        details = []
        for err in exc.errors():
            loc = [str(p) for p in err["loc"] if p != "body"]
            field = loc[-1] if loc else "body"
            details.append(
                {"field": field, "message": _friendly(field, err["type"], err["msg"], err.get("ctx") or {})}
            )
        summary = details[0]["message"] if len(details) == 1 else "Some fields are invalid; see 'details' for what to fix."
        return JSONResponse(status_code=422, content=_body(request, "validation_error", summary, details))

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        messages = {404: "Resource not found.", 405: "Method not allowed."}
        body = _body(request, f"http_{exc.status_code}", messages.get(exc.status_code, "Request failed."))
        return JSONResponse(status_code=exc.status_code, content=body)

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        logger.error("unhandled error", exc_info=exc, extra={"path": request.url.path})
        body = _body(request, "internal_error", "Something went wrong on our side. Please try again later.")
        return JSONResponse(status_code=500, content=body)

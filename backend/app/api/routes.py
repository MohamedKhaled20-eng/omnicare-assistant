"""HTTP routes: POST /api/v1/chat and GET /api/v1/health."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request

from app.agent.graph import CustomerAssistant
from app.api.schemas import ChatRequest, ChatResponse, ErrorResponse, HealthResponse
from app.core.errors import AppError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1")


@router.get("/health", response_model=HealthResponse, tags=["system"])
def health() -> HealthResponse:
    return HealthResponse(status="healthy")


@router.post(
    "/chat",
    response_model=ChatResponse,
    responses={422: {"model": ErrorResponse}, 502: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
    tags=["chat"],
)
def chat(body: ChatRequest, request: Request) -> ChatResponse:
    # Sync endpoint: FastAPI runs it in a worker thread, so blocking LLM calls don't stall the event loop.
    assistant: CustomerAssistant | None = request.app.state.assistant
    if assistant is None:
        raise AppError(
            503,
            "assistant_unavailable",
            "The assistant is not configured yet. Please contact the administrator.",
        )
    try:
        result = assistant.chat(body.user_id, body.message)
    except Exception as exc:
        logger.exception("agent failure", extra={"user_id": body.user_id})
        raise AppError(
            502, "assistant_error", "The assistant is temporarily unavailable. Please try again in a moment."
        ) from exc

    logger.info(
        "chat handled",
        extra={"user_id": body.user_id, "tools": [c["name"] for c in result.tool_calls], "sources": len(result.sources)},
    )
    return ChatResponse(response=result.response, sources=result.sources, tool_calls=result.tool_calls)

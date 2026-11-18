"""Request/response models for the public REST API."""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

MAX_MESSAGE_LENGTH = 2000

UserId = Annotated[
    str,
    StringConstraints(strip_whitespace=True, pattern=r"^usr_[A-Za-z0-9_-]{1,64}$"),
]
Message = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_MESSAGE_LENGTH),
]


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: UserId = Field(examples=["usr_123"])
    message: Message = Field(examples=["Are burst pipes covered?"])


class ToolCall(BaseModel):
    name: str
    arguments: dict[str, Any]
    result: Any


class ChatResponse(BaseModel):
    response: str
    sources: list[str]
    tool_calls: list[ToolCall]


class HealthResponse(BaseModel):
    status: str = "healthy"


class ErrorDetail(BaseModel):
    code: str
    message: str
    request_id: str | None = None
    details: list[dict[str, str]] | None = None


class ErrorResponse(BaseModel):
    error: ErrorDetail

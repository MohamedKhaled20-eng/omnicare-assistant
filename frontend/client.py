"""Thin HTTP client for the backend `POST /api/v1/chat` endpoint."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

import requests

DEFAULT_TIMEOUT_SECONDS = 90


def new_user_id() -> str:
    return f"usr_{uuid.uuid4().hex[:8]}"


@dataclass
class ChatReply:
    response: str
    sources: list[str] = field(default_factory=list)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)


class ChatError(Exception):
    """A failure that is safe to show to the end user."""


def _error_message(res: requests.Response) -> str:
    try:
        error = res.json()["error"]
    except (ValueError, KeyError, TypeError):
        return f"The assistant returned an unexpected error (HTTP {res.status_code}). Please try again."
    if res.status_code == 422 and error.get("details"):
        return " ".join(d["message"] for d in error["details"])
    return str(error.get("message") or "The assistant could not process your request.")


def send_chat(backend_url: str, user_id: str, message: str, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> ChatReply:
    url = f"{backend_url.rstrip('/')}/api/v1/chat"
    try:
        res = requests.post(url, json={"user_id": user_id, "message": message}, timeout=timeout)
    except requests.ConnectionError as exc:
        raise ChatError("I can't reach the assistant service right now. Please check that the backend is running.") from exc
    except requests.Timeout as exc:
        raise ChatError("The assistant is taking too long to respond. Please try again in a moment.") from exc
    except requests.RequestException as exc:
        raise ChatError("Something went wrong while contacting the assistant. Please try again.") from exc

    if res.status_code != 200:
        raise ChatError(_error_message(res))
    try:
        data = res.json()
        return ChatReply(
            response=str(data["response"]),
            sources=list(data.get("sources", [])),
            tool_calls=list(data.get("tool_calls", [])),
        )
    except (ValueError, KeyError, TypeError) as exc:
        raise ChatError("The assistant sent a response I couldn't read. Please try again.") from exc

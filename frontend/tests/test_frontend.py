from __future__ import annotations

from pathlib import Path

import pytest
import requests
from streamlit.testing.v1 import AppTest

import client
from client import ChatError, ChatReply, send_chat

APP = str(Path(__file__).resolve().parents[1] / "app.py")


class FakeResponse:
    def __init__(self, status: int, payload=None, bad_json: bool = False) -> None:
        self.status_code, self._payload, self._bad = status, payload, bad_json

    def json(self):
        if self._bad:
            raise ValueError("no json")
        return self._payload


def patch_post(monkeypatch: pytest.MonkeyPatch, result) -> list[dict]:
    seen: list[dict] = []

    def fake_post(url, json=None, timeout=None):
        seen.append({"url": url, "json": json, "timeout": timeout})
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(client.requests, "post", fake_post)
    return seen


def test_send_chat_posts_to_chat_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = patch_post(
        monkeypatch,
        FakeResponse(200, {"response": "hi", "sources": ["s"], "tool_calls": [{"name": "t", "arguments": {}, "result": 1}]}),
    )
    reply = send_chat("http://backend:8000/", "usr_1", "hello")
    assert seen[0]["url"] == "http://backend:8000/api/v1/chat"
    assert seen[0]["json"] == {"user_id": "usr_1", "message": "hello"}
    assert reply == ChatReply("hi", ["s"], [{"name": "t", "arguments": {}, "result": 1}])


@pytest.mark.parametrize(
    ("result", "fragment"),
    [
        (requests.ConnectionError(), "can't reach"),
        (requests.Timeout(), "too long"),
        (requests.RequestException(), "Something went wrong"),
        (FakeResponse(503, {"error": {"code": "x", "message": "Assistant not configured."}}), "not configured"),
        (
            FakeResponse(422, {"error": {"details": [{"field": "message", "message": "Message must not be empty."}]}}),
            "must not be empty",
        ),
        (FakeResponse(500, bad_json=True), "HTTP 500"),
        (FakeResponse(200, {"unexpected": 1}), "couldn't read"),
    ],
)
def test_send_chat_errors_are_friendly(monkeypatch: pytest.MonkeyPatch, result, fragment: str) -> None:
    patch_post(monkeypatch, result)
    with pytest.raises(ChatError, match=fragment):
        send_chat("http://x", "usr_1", "hello")


def test_user_ids_match_backend_format() -> None:
    import re

    assert re.fullmatch(r"usr_[a-f0-9]{8}", client.new_user_id())
    assert client.new_user_id() != client.new_user_id()


def test_ui_shows_history_sources_and_tool_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[tuple[str, str]] = []

    def fake_send(url: str, user_id: str, message: str) -> ChatReply:
        sent.append((user_id, message))
        return ChatReply(
            "Covered up to $25,000.",
            ["sample_policy.md — Section 1: Home Water Damage Coverage"],
            [{"name": "search_policy", "arguments": {"query": message}, "result": {"sections": []}}],
        )

    monkeypatch.setattr(client, "send_chat", fake_send)
    at = AppTest.from_file(APP, default_timeout=15).run()
    assert not at.exception
    user_id = at.session_state["user_id"]

    at.chat_input[0].set_value("Are burst pipes covered?").run()
    at.chat_input[0].set_value("And floods?").run()

    assert not at.exception
    assert [m["role"] for m in at.session_state["messages"]] == ["assistant", "user", "assistant", "user", "assistant"]
    assert {uid for uid, _ in sent} == {user_id}  # stable user id for the whole session
    assert any("Section 1" in c.value for c in at.caption)
    assert any("search_policy" in e.label or "Tools used" in e.label for e in at.expander)


def test_ui_shows_friendly_error_and_keeps_going(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_args) -> ChatReply:
        raise ChatError("I can't reach the assistant service right now.")

    monkeypatch.setattr(client, "send_chat", boom)
    at = AppTest.from_file(APP, default_timeout=15).run()
    at.chat_input[0].set_value("hello").run()

    assert not at.exception
    assert any("can't reach" in e.value for e in at.error)


def test_new_conversation_resets_state(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(client, "send_chat", lambda *_: ChatReply("ok"))
    at = AppTest.from_file(APP, default_timeout=15).run()
    first_id = at.session_state["user_id"]
    at.chat_input[0].set_value("hi").run()
    at.sidebar.button[0].click().run()

    assert at.session_state["user_id"] != first_id
    assert len(at.session_state["messages"]) == 1

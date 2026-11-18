"""OmniCare Financial customer assistant - Streamlit chat UI.

Talks to the backend exclusively through POST {BACKEND_URL}/api/v1/chat.
"""

from __future__ import annotations

import os
from typing import Any

import streamlit as st

from client import ChatError, new_user_id, send_chat

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

GREETING = (
    "Hi! I'm the OmniCare assistant. I can answer questions about your policy coverage, "
    "check the status of a claim, or help you file a new one."
)
EXAMPLES = [
    "Are burst pipes covered?",
    "What about gradual leaks or floods?",
    "Do I need receipts for my jewelry?",
    "What's the status of CLM-8821?",
    "I want to file a claim",
]


def reset_conversation() -> None:
    st.session_state.user_id = new_user_id()
    st.session_state.messages = [{"role": "assistant", "content": GREETING}]
    st.session_state.pending = None


def init_state() -> None:
    if "user_id" not in st.session_state:
        reset_conversation()


def render_details(message: dict[str, Any]) -> None:
    if sources := message.get("sources"):
        st.caption("📎 **Sources**")
        for source in sources:
            st.caption(f"• {source}")
    if calls := message.get("tool_calls"):
        with st.expander(f"🔧 Tools used ({len(calls)})"):
            for call in calls:
                st.markdown(f"**{call['name']}**")
                st.caption("Arguments")
                st.json(call.get("arguments", {}))
                st.caption("Result")
                st.json(call.get("result"))


def render_history() -> None:
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            if message.get("is_error"):
                st.error(message["content"])
            else:
                st.markdown(message["content"])
            render_details(message)


def handle_prompt(prompt: str) -> None:
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
    with st.chat_message("assistant"):
        try:
            with st.spinner("Looking into that…"):
                reply = send_chat(BACKEND_URL, st.session_state.user_id, prompt)
            entry = {
                "role": "assistant",
                "content": reply.response,
                "sources": reply.sources,
                "tool_calls": reply.tool_calls,
            }
        except ChatError as exc:
            entry = {"role": "assistant", "content": str(exc), "is_error": True}
    st.session_state.messages.append(entry)
    st.rerun()


def main() -> None:
    st.set_page_config(page_title="OmniCare Assistant", page_icon="🛡️")
    init_state()

    st.title("🛡️ OmniCare Customer Assistant")
    with st.sidebar:
        st.subheader("Session")
        st.caption(f"User ID: `{st.session_state.user_id}`")
        if st.button("➕ New conversation", use_container_width=True):
            reset_conversation()
            st.rerun()
        st.subheader("Try asking")
        for example in EXAMPLES:
            if st.button(example, use_container_width=True, key=f"ex_{example}"):
                st.session_state.pending = example
                st.rerun()

    render_history()

    prompt = st.chat_input("Ask about coverage, check a claim, or file a new one…", max_chars=2000)
    if not prompt and st.session_state.pending:
        prompt, st.session_state.pending = st.session_state.pending, None
    if prompt and prompt.strip():
        handle_prompt(prompt.strip())


main()

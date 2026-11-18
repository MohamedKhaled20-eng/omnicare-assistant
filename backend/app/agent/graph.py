"""LangGraph workflow: guardrail -> agent <-> tools -> final answer, with per-user memory."""

from __future__ import annotations

import logging
import re
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    AnyMessage,
    HumanMessage,
    RemoveMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.tools import BaseTool
from langgraph.checkpoint.memory import MemorySaver
from langgraph.errors import GraphRecursionError
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode

from app.agent.prompts import SYSTEM_PROMPT
from app.safety.guardrails import REFUSAL_MESSAGE, check_input

logger = logging.getLogger(__name__)

MAX_HISTORY_MESSAGES = 30
FALLBACK_RESPONSE = (
    "I'm sorry, I wasn't able to complete that request. Please try rephrasing it, "
    "or contact OmniCare support for help."
)


class AgentState(MessagesState):
    blocked: bool
    refusal: str


@dataclass
class ChatResult:
    response: str
    sources: list[str] = field(default_factory=list)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)


def _message_text(content: Any) -> str:
    """Normalise message content (some providers return a list of content blocks)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        blocks = [
            block if isinstance(block, str) else block.get("text", "")
            for block in content
            if isinstance(block, (str, dict))
        ]
        return "".join(blocks)
    return str(content or "")


def _tool_error_message(exc: Exception) -> str:
    logger.warning("tool execution error", extra={"error_type": type(exc).__name__})
    return (
        "The tool call was invalid or failed. Check the argument names and values, "
        "or ask the user for the missing information."
    )


def _recent_messages(messages: list[AnyMessage]) -> list[AnyMessage]:
    """Keep recent history, never starting on an orphaned tool result / tool-call reply."""
    if len(messages) <= MAX_HISTORY_MESSAGES:
        return messages
    recent = messages[-MAX_HISTORY_MESSAGES:]
    while recent and not isinstance(recent[0], HumanMessage):
        recent = recent[1:]
    return recent


def build_graph(model: BaseChatModel, tools: list[BaseTool]):
    tool_enabled_model = model.bind_tools(tools)

    def guardrail(state: AgentState) -> dict[str, Any]:
        latest_message = state["messages"][-1]
        verdict = check_input(_message_text(latest_message.content))
        if not verdict.blocked:
            return {"blocked": False, "refusal": ""}
        logger.warning("prompt injection blocked", extra={"category": verdict.category})
        return {
            "blocked": True,
            "refusal": REFUSAL_MESSAGE,
            "messages": [RemoveMessage(id=latest_message.id)],
        }

    def agent(state: AgentState) -> dict[str, Any]:
        prompt = [SystemMessage(content=SYSTEM_PROMPT), *_recent_messages(state["messages"])]
        return {"messages": [tool_enabled_model.invoke(prompt)]}

    def after_guardrail(state: AgentState) -> str:
        return END if state["blocked"] else "agent"

    def after_agent(state: AgentState) -> str:
        latest_message = state["messages"][-1]
        return "tools" if isinstance(latest_message, AIMessage) and latest_message.tool_calls else END

    graph = StateGraph(AgentState)
    graph.add_node("guardrail", guardrail)
    graph.add_node("agent", agent)
    graph.add_node("tools", ToolNode(tools, handle_tool_errors=_tool_error_message))
    graph.add_edge(START, "guardrail")
    graph.add_conditional_edges("guardrail", after_guardrail, {END: END, "agent": "agent"})
    graph.add_conditional_edges("agent", after_agent, {"tools": "tools", END: END})
    graph.add_edge("tools", "agent")
    return graph.compile(checkpointer=MemorySaver())


class CustomerAssistant:
    """Facade used by the API layer. `user_id` is the LangGraph thread id (per-user memory)."""

    def __init__(self, llm: BaseChatModel, tools: list[BaseTool], recursion_limit: int = 12) -> None:
        self._graph = build_graph(llm, tools)
        self._recursion_limit = recursion_limit
        self._user_locks: defaultdict[str, threading.Lock] = defaultdict(threading.Lock)
        self._locks_guard = threading.Lock()

    def _lock_for(self, user_id: str) -> threading.Lock:
        with self._locks_guard:
            return self._user_locks[user_id]

    def chat(self, user_id: str, message: str) -> ChatResult:
        config = {"configurable": {"thread_id": user_id}, "recursion_limit": self._recursion_limit}
        with self._lock_for(user_id):
            try:
                state = self._graph.invoke(
                    {"messages": [HumanMessage(content=message)], "blocked": False, "refusal": ""},
                    config,
                )
            except GraphRecursionError:
                logger.error("agent recursion limit reached")
                return ChatResult(response=FALLBACK_RESPONSE)

        if state.get("blocked"):
            return ChatResult(response=state["refusal"])
        return self._build_result(state["messages"])

    @staticmethod
    def _build_result(messages: list[AnyMessage]) -> ChatResult:
        last_human = max((i for i, m in enumerate(messages) if isinstance(m, HumanMessage)), default=-1)
        turn = messages[last_human + 1 :]

        results: dict[str, ToolMessage] = {
            message.tool_call_id: message for message in turn if isinstance(message, ToolMessage)
        }
        tool_calls: list[dict[str, Any]] = []
        retrieved_sources: list[str] = []
        for assistant_message in turn:
            if not isinstance(assistant_message, AIMessage):
                continue
            for call in assistant_message.tool_calls:
                tool_message = results.get(call["id"])
                artifact = tool_message.artifact if tool_message is not None else None
                if isinstance(artifact, dict):
                    result: Any = artifact.get("result")
                    retrieved_sources.extend(artifact.get("sources", []))
                else:  # tool raised -> ToolNode produced a plain error message
                    result = {
                        "error": _message_text(tool_message.content) if tool_message else "No result."
                    }
                tool_calls.append({"name": call["name"], "arguments": call["args"], "result": result})

        final_message = turn[-1] if turn else None
        answer = _message_text(final_message.content).strip() if isinstance(final_message, AIMessage) else ""
        if not answer:
            return ChatResult(response=FALLBACK_RESPONSE, tool_calls=tool_calls)

        sources = _select_sources(answer, retrieved_sources)
        return ChatResult(response=_ensure_citations(answer, sources), sources=sources, tool_calls=tool_calls)


def _label(citation: str) -> str:
    """'sample_policy.md — Section 1: Title' -> 'section 1'."""
    return citation.split("—", 1)[-1].split(":", 1)[0].strip().lower()


def _is_cited(answer: str, citation: str) -> bool:
    section = citation.split("—", 1)[-1].strip().lower()
    return section in answer.lower() or _label(citation) in answer.lower().replace("§", "section ")


_DECLINE = re.compile(
    r"(?:contact|reach out to|call)\s+(?:omnicare\s+)?(?:customer\s+)?support|"
    r"(?:couldn'?t|could not|can'?t|cannot|unable to)\s+find|"
    r"\bno\s+(?:relevant\s+)?(?:information|details)|"
    r"not\s+(?:mentioned|specified|addressed|covered\s+in)",
    re.IGNORECASE,
)


def _select_sources(answer: str, retrieved: list[str]) -> list[str]:
    """Sources = retrieved sections the answer cites. If it cites none, fall back to the
    best-ranked hit unless the answer is a "not covered / contact support" decline."""
    unique = list(dict.fromkeys(retrieved))
    cited = [source for source in unique if _is_cited(answer, source)]
    if cited or not unique or _DECLINE.search(answer):
        return cited
    return unique[:1]


def _ensure_citations(answer: str, sources: list[str]) -> str:
    missing = [source for source in sources if not _is_cited(answer, source)]
    if not missing:
        return answer
    return answer + "\n\nSources:\n" + "\n".join(f"- {source}" for source in missing)

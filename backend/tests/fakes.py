"""Offline test doubles: a lexical hashing embedder and a rule-based fake chat model."""

from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage, ToolMessage

_STOPWORDS = {
    "a", "an", "and", "are", "as", "be", "by", "can", "do", "does", "for", "i", "if", "in", "is",
    "it", "my", "of", "on", "or", "the", "to", "up", "what", "with", "about", "need", "have",
}
DIM = 512


def _tokens(text: str) -> list[str]:
    words = re.findall(r"[a-z0-9$,]+", text.lower())
    out = []
    for w in words:
        w = w.strip(",")
        if not w or w in _STOPWORDS:
            continue
        if len(w) > 3 and w.endswith("s"):  # crude stemming: pipes -> pipe, bursts -> burst
            w = w[:-1]
        out.append(w)
    return out


class HashingEmbedder:
    """Deterministic bag-of-words embedder (unit-norm), so cosine distance is meaningful offline."""

    def _embed(self, text: str) -> list[float]:
        vec = [0.0] * DIM
        for tok in _tokens(text):
            idx = int(hashlib.md5(tok.encode()).hexdigest(), 16) % DIM
            vec[idx] += 1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)


_FIELD_PAIR = re.compile(r"(policy|type|amount|description)\s*:\s*([^,\n]+)", re.IGNORECASE)
_CLAIM_INTENT = re.compile(r"file a claim|submit a claim|new claim", re.IGNORECASE)
_REQUIRED = ("policy", "type", "amount", "description")
_FIELD_TO_ARG = {"policy": "policy_number", "type": "claim_type", "amount": "amount", "description": "description"}


class FakeChatModel:
    """Stands in for the LLM: decides tool calls with simple rules and answers from tool output."""

    def __init__(self) -> None:
        self.calls: list[list[AnyMessage]] = []
        self.bound_tools: list[str] = []
        self._n = 0

    def bind_tools(self, tools: list[Any]) -> "FakeChatModel":
        self.bound_tools = [t.name for t in tools]
        return self

    # --- helpers ---------------------------------------------------------
    def _call(self, name: str, args: dict[str, Any]) -> AIMessage:
        self._n += 1
        return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": f"call_{self._n}"}])

    def invoke(self, messages: list[AnyMessage]) -> AIMessage:
        self.calls.append(messages)
        assert isinstance(messages[0], SystemMessage), "system prompt must lead every LLM call"
        last = messages[-1]
        if isinstance(last, ToolMessage):
            return self._answer_from_tool(last)

        text = str(last.content)
        if m := re.search(r"CLM-\d+", text, re.IGNORECASE):
            return self._call("get_claim_status", {"claim_id": m.group(0)})
        turn_humans = self._humans_since_last_submission(messages)
        if any(_CLAIM_INTENT.search(h) for h in turn_humans):
            return self._claim_flow(turn_humans)
        return self._call("search_policy", {"query": text})

    @staticmethod
    def _humans_since_last_submission(messages: list[AnyMessage]) -> list[str]:
        start = 0
        for i, m in enumerate(messages):
            if isinstance(m, ToolMessage) and m.name == "submit_claim":
                start = i + 1
        return [str(m.content) for m in messages[start:] if isinstance(m, HumanMessage)]

    def _claim_flow(self, humans: list[str]) -> AIMessage:
        fields: dict[str, str] = {}
        for h in humans:
            for key, value in _FIELD_PAIR.findall(h):
                fields[key.lower()] = value.strip()
        missing = [f for f in _REQUIRED if f not in fields]
        if missing:
            labels = {"policy": "policy number", "type": "claim type", "amount": "amount", "description": "description"}
            return AIMessage(content="To file your claim I still need: " + ", ".join(labels[f] for f in missing) + ".")
        return self._call("submit_claim", {_FIELD_TO_ARG[k]: fields[k] for k in _REQUIRED})

    @staticmethod
    def _answer_from_tool(msg: ToolMessage) -> AIMessage:
        assert "<untrusted_data" in str(msg.content), "tool output must be marked untrusted"
        result = (msg.artifact or {}).get("result", {})
        if msg.name == "search_policy":
            sections = result.get("sections", [])
            if not sections:
                return AIMessage(content="The policy documents don't cover that. Please contact OmniCare support.")
            top = sections[0]
            return AIMessage(content=f"{top['text']} (Source: {top['citation']})")
        if msg.name == "get_claim_status":
            if not result["found"]:
                return AIMessage(content=f"Sorry, {result['message']}")
            c = result["claim"]
            return AIMessage(
                content=f"Claim {c['claim_id']} ({c['claim_type']}, policy {c['policy_number']}) is {c['status']} "
                f"for {c['amount_formatted']}."
            )
        if msg.name == "submit_claim":
            if result["success"]:
                return AIMessage(content=f"Done! {result['message']}")
            return AIMessage(content="I couldn't submit it: " + " ".join(result["errors"]))
        return AIMessage(content=json.dumps(result))

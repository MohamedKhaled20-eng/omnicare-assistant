"""LangChain tool wrappers. Each tool returns (text for the LLM, artifact for the API).

The text is wrapped in <untrusted_data> tags so the model treats it as data, not instructions.
The artifact carries the raw result (recorded in `tool_calls`) and, for retrieval, citation sources.
"""

from __future__ import annotations

import json
import re
from typing import Any

from langchain_core.tools import BaseTool, tool

from app.rag.retriever import PolicyRetriever
from app.tools.claims import ClaimsRepository, get_claim_status, submit_claim

_CLOSING_TAG = re.compile(r"<\s*/\s*untrusted_data\s*>", re.IGNORECASE)


def wrap_untrusted(kind: str, content: str) -> str:
    content = _CLOSING_TAG.sub("[removed]", content)
    return f'<untrusted_data kind="{kind}">\n{content}\n</untrusted_data>'


def build_tools(
    repository: ClaimsRepository,
    retriever: PolicyRetriever,
    max_distance: float | None = None,
) -> list[BaseTool]:
    @tool("search_policy", response_format="content_and_artifact")
    def search_policy(query: str) -> tuple[str, dict[str, Any]]:
        """Search the official OmniCare policy documents. Use for any question about coverage,
        limits, deductibles, exclusions or required documentation. Input: a short search query
        in plain English."""
        sections = retriever.search(query)
        if max_distance is not None:
            sections = [section for section in sections if section.distance <= max_distance]
        if not sections:
            text = "No relevant policy sections were found."
        else:
            text = "\n\n".join(
                f"[Citation: {section.citation}]\n{section.text}" for section in sections
            )
        result = {
            "query": query,
            "sections": [
                {
                    "citation": section.citation,
                    "text": section.text,
                    "distance": round(section.distance, 4),
                }
                for section in sections
            ],
        }
        return wrap_untrusted("policy_search", text), {
            "result": result,
            "sources": [section.citation for section in sections],
        }

    @tool("get_claim_status", response_format="content_and_artifact")
    def get_claim_status_tool(claim_id: str) -> tuple[str, dict[str, Any]]:
        """Look up the status of an existing claim by its claim ID (format CLM-1234)."""
        result = get_claim_status(repository, claim_id).model_dump()
        return wrap_untrusted("claim_status", json.dumps(result)), {"result": result, "sources": []}

    @tool("submit_claim", response_format="content_and_artifact")
    def submit_claim_tool(
        policy_number: str, claim_type: str, amount: float | str, description: str
    ) -> tuple[str, dict[str, Any]]:
        """Submit a new insurance claim. Call ONLY after the user has provided all four fields.
        policy_number: format POL-1234. claim_type: 'Water Damage' or 'Personal Property'.
        amount: positive number with at most 2 decimals (e.g. 1250.00). description: short
        summary of what happened."""
        result = submit_claim(repository, policy_number, claim_type, amount, description).model_dump()
        return wrap_untrusted("claim_submission", json.dumps(result)), {"result": result, "sources": []}

    return [search_policy, get_claim_status_tool, submit_claim_tool]

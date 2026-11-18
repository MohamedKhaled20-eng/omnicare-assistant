"""Heuristic prompt-injection pre-filter. Runs before any LLM call or tool execution.

This is one layer of defence: the system prompt is hardened too, and retrieved documents /
tool outputs are always passed to the model as untrusted data.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

REFUSAL_MESSAGE = (
    "I'm sorry, but I can't help with that request. I can answer questions about your "
    "OmniCare policy coverage, check the status of a claim, or help you submit a new claim. "
    "How can I help with one of those?"
)

_ZERO_WIDTH = dict.fromkeys(map(ord, "\u200b\u200c\u200d\u2060\ufeff\u00ad"))

_WORDS = r"(?:\w+\s+){0,3}"  # up to three filler words, e.g. "all of the"

_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "instruction_override",
        re.compile(
            r"\b(?:ignore|disregard|forget|override|bypass|skip|drop|discard)\s+"
            + _WORDS
            + r"(?:previous|prior|above|earlier|preceding|former|existing|system|initial|original|your|any|all)\s+"
            + _WORDS
            + r"(?:instructions?|prompts?|rules?|guidelines?|directives?|context|messages?|restrictions?|programming|constraints?)"
        ),
    ),
    (
        "new_instructions",
        re.compile(
            r"\b(?:new|updated|revised)\s+(?:system\s+)?instructions?\s*:|"
            r"\bfrom\s+now\s+on,?\s+(?:you|ignore|act|respond|answer|only)\b|"
            r"\byou\s+(?:are|will)\s+now\s+(?:a|an|the|in|no\s+longer)\b|"
            r"\byou\s+are\s+no\s+longer\b"
        ),
    ),
    (
        "prompt_exfiltration",
        re.compile(
            r"\b(?:reveal|show|print|display|repeat|output|leak|expose|dump|tell\s+me|give\s+me|share|disclose|recite|summari[sz]e|what\s+(?:is|are))\s+"
            + _WORDS
            + r"(?:system|initial|hidden|secret|internal|developer|original|underlying|your)\s+"
            + _WORDS
            + r"(?:prompts?|instructions?|messages?|rules|guidelines|configuration|config|settings)"
        ),
    ),
    (
        "secret_exfiltration",
        re.compile(
            r"\b(?:reveal|show|print|display|leak|expose|dump|tell\s+me|give\s+me|share|what\s+(?:is|are))\s+"
            + _WORDS
            + r"(?:api[\s_-]?keys?|secrets?|credentials?|passwords?|tokens?|environment\s+variables?|env\s+vars?)"
        ),
    ),
    (
        "fake_role_tags",
        re.compile(
            r"<\s*/?\s*(?:system|assistant|developer|instructions?)\s*>|"
            r"\[\s*/?\s*(?:system|assistant|developer|inst)\s*\]|"
            r"<\|\s*(?:im_start|im_end|system|assistant|endoftext)\s*\|>|"
            r"^\s*#{1,6}\s*(?:system|developer)\b|"
            r"(?:^|\n)\s*(?:system|developer|assistant)\s*(?:prompt|message)?\s*:|"
            r"\brole\s*[\"']?\s*[:=]\s*[\"']?(?:system|developer)\b"
        ),
    ),
    (
        "jailbreak",
        re.compile(
            r"\bjailbreak|\bjail\s*break|\bdan\s+mode\b|\bdo\s+anything\s+now\b|\bdeveloper\s+mode\b|"
            r"\bgod\s+mode\b|\bsudo\s+mode\b|"
            r"\b(?:pretend|act|behave|roleplay|role-play)\s+(?:as\s+(?:if\s+)?|like\s+|that\s+)?(?:you\s+(?:are|have|were)\s+)?(?:an?\s+)?(?:unrestricted|unfiltered|uncensored|evil|rogue)|"
            r"\bwithout\s+(?:any\s+)?(?:restrictions|limitations|filters|guardrails|safety)\b|"
            r"\b(?:disable|turn\s+off|remove|deactivate)\s+(?:your\s+|all\s+|the\s+)?(?:safety|guardrails?|filters?|restrictions|content\s+polic(?:y|ies))"
        ),
    ),
)


@dataclass(frozen=True)
class GuardrailResult:
    blocked: bool
    category: str | None = None


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).translate(_ZERO_WIDTH)
    return re.sub(r"[ \t\r\f\v]+", " ", text).lower()


def check_input(text: str) -> GuardrailResult:
    """Return `blocked=True` with the matched category when the text looks like prompt injection."""
    normalized = _normalize(text)
    # Also test a de-punctuated variant so "i.g.n.o.r.e"-style or "ignore, previous" tricks still match.
    variants = (normalized, re.sub(r"[^\w\s<>\[\]|:#\"'=/-]", " ", normalized))
    for category, pattern in _RULES:
        if any(pattern.search(v) for v in variants):
            return GuardrailResult(blocked=True, category=category)
    return GuardrailResult(blocked=False)

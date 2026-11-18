"""Provider-agnostic chat model factory (provider SDKs are imported lazily)."""

from __future__ import annotations

from langchain_core.language_models.chat_models import BaseChatModel

from app.core.config import Settings


class LLMConfigurationError(RuntimeError):
    """The selected LLM provider is not usable (e.g. missing API key)."""


def _require_key(settings: Settings) -> str:
    secret = getattr(settings, f"{settings.llm_provider}_api_key")
    key = secret.get_secret_value().strip() if secret else ""
    if not key:
        raise LLMConfigurationError(
            f"LLM_PROVIDER={settings.llm_provider} requires {settings.llm_provider.upper()}_API_KEY to be set."
        )
    return key


def build_llm(settings: Settings) -> BaseChatModel:
    provider, model = settings.llm_provider, settings.resolved_llm_model
    common = {"temperature": settings.llm_temperature}

    if provider == "groq":
        from langchain_groq import ChatGroq

        return ChatGroq(model=model, api_key=_require_key(settings), timeout=settings.llm_timeout_seconds, max_retries=2, **common)
    if provider == "openai":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(model=model, api_key=_require_key(settings), timeout=settings.llm_timeout_seconds, max_retries=2, **common)
    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(model=model, api_key=_require_key(settings), timeout=settings.llm_timeout_seconds, max_retries=2, max_tokens=1024, **common)
    if provider == "ollama":
        from langchain_ollama import ChatOllama

        return ChatOllama(model=model, base_url=settings.ollama_base_url, **common)
    raise LLMConfigurationError(f"Unsupported LLM_PROVIDER: {provider}")

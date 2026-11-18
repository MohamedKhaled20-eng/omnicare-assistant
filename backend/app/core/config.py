"""Application settings, loaded from environment variables / a `.env` file."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]

LLMProvider = Literal["groq", "openai", "anthropic", "ollama"]

DEFAULT_MODELS: dict[str, str] = {
    "groq": "llama-3.3-70b-versatile",
    "openai": "gpt-4o-mini",
    "anthropic": "claude-3-5-haiku-latest",
    "ollama": "llama3.1",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- LLM -----------------------------------------------------------
    llm_provider: LLMProvider = "groq"
    llm_model: str = ""  # empty -> provider default (see DEFAULT_MODELS)
    llm_temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    llm_timeout_seconds: float = Field(default=60.0, gt=0)
    groq_api_key: SecretStr | None = None
    openai_api_key: SecretStr | None = None
    anthropic_api_key: SecretStr | None = None
    ollama_base_url: str = "http://localhost:11434"

    # --- Data & persistence ---------------------------------------------
    policy_file_path: Path = BACKEND_DIR / "data" / "sample_policy.md"
    claims_seed_path: Path = BACKEND_DIR / "data" / "mock_claims.json"
    # Working copy of the claims store; seeded from `claims_seed_path` when missing.
    claims_file_path: Path = BACKEND_DIR / "storage" / "mock_claims.json"
    chroma_path: Path = BACKEND_DIR / "storage" / "chroma"
    chroma_collection: str = "policy_sections"

    # --- RAG -------------------------------------------------------------
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    rag_top_k: int = Field(default=3, ge=1, le=10)
    # Cosine distance above which a section is considered irrelevant (0 = identical, 2 = opposite).
    rag_max_distance: float = Field(default=0.5, gt=0, le=2.0)

    # --- API -------------------------------------------------------------
    cors_origins: str = "http://localhost:8501,http://127.0.0.1:8501"
    agent_recursion_limit: int = Field(default=12, ge=3)
    log_level: str = "INFO"

    @property
    def resolved_llm_model(self) -> str:
        return self.llm_model.strip() or DEFAULT_MODELS[self.llm_provider]

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()

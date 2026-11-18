from __future__ import annotations

import shutil
from pathlib import Path
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from app.core.config import BACKEND_DIR, Settings
from app.main import create_app
from app.rag.ingest import get_collection, ingest_policy
from app.rag.retriever import PolicyRetriever
from app.tools.claims import ClaimsRepository
from tests.fakes import FakeChatModel, HashingEmbedder

REAL_POLICY = BACKEND_DIR / "data" / "sample_policy.md"
REAL_SEED = BACKEND_DIR / "data" / "mock_claims.json"


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Keep the default run fully offline: real-model tests only run with `-m real_embeddings`."""
    if "real_embeddings" in (config.getoption("-m") or ""):
        return
    skip = pytest.mark.skip(reason="opt-in: run with `pytest -m real_embeddings`")
    for item in items:
        if "real_embeddings" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(autouse=True)
def _isolate_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Developer shell variables / .env must never leak into tests (no real keys, no real paths)."""
    for var in ("LLM_PROVIDER", "LLM_MODEL", "GROQ_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
def claims_file(tmp_path: Path) -> Path:
    """Temp copy of the seed data; the real mock_claims.json is never touched."""
    path = tmp_path / "claims" / "mock_claims.json"
    path.parent.mkdir()
    shutil.copyfile(REAL_SEED, path)
    return path


@pytest.fixture
def settings(tmp_path: Path, claims_file: Path) -> Settings:
    return Settings(
        _env_file=None,
        policy_file_path=REAL_POLICY,
        claims_seed_path=REAL_SEED,
        claims_file_path=claims_file,
        chroma_path=tmp_path / "chroma",
        rag_max_distance=0.95,  # hashing embedder: unrelated text sits at distance 1.0
        cors_origins="http://localhost:8501",
    )


@pytest.fixture
def repo(claims_file: Path) -> ClaimsRepository:
    return ClaimsRepository(claims_file, REAL_SEED)


@pytest.fixture
def embedder() -> HashingEmbedder:
    return HashingEmbedder()


@pytest.fixture
def retriever(tmp_path: Path, embedder: HashingEmbedder) -> PolicyRetriever:
    collection = get_collection(tmp_path / "chroma_rag", "policy_test")
    ingest_policy(REAL_POLICY, collection, embedder)
    return PolicyRetriever(collection, embedder, top_k=3)


@pytest.fixture
def fake_llm() -> FakeChatModel:
    return FakeChatModel()


@pytest.fixture
def client(settings: Settings, fake_llm: FakeChatModel, embedder: HashingEmbedder) -> Iterator[TestClient]:
    app = create_app(settings, llm=fake_llm, embedder=embedder)
    with TestClient(app) as test_client:  # `with` runs the lifespan (ingestion + wiring)
        yield test_client

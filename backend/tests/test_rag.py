from __future__ import annotations

from pathlib import Path

import pytest

from app.rag.ingest import get_collection, ingest_policy, parse_policy_sections
from app.rag.retriever import PolicyRetriever
from tests.conftest import REAL_POLICY
from tests.fakes import HashingEmbedder

SECTION_1 = "Section 1: Home Water Damage Coverage"
SECTION_2 = "Section 2: Personal Property Protection"


def test_chunks_by_h2_heading_with_metadata() -> None:
    sections = parse_policy_sections(REAL_POLICY.read_text(), "sample_policy.md")

    assert [s.section for s in sections] == [SECTION_1, SECTION_2]
    assert all(s.source == "sample_policy.md" for s in sections)
    assert all(s.document_title == "OmniCare General Insurance Policy 2026" for s in sections)
    assert "$25,000" in sections[0].text and "$500 deductible" in sections[0].text
    assert "appraisal receipts" in sections[1].text
    assert not any("#" in s.text for s in sections)


@pytest.mark.parametrize(
    ("query", "expected_section", "expected_fragments"),
    [
        ("Are burst pipes covered?", SECTION_1, ["$25,000", "$500 deductible"]),
        ("What about gradual leaks or floods?", SECTION_1, ["Gradual leaks", "strictly excluded"]),
        ("Do I need receipts for my jewelry?", SECTION_2, ["$10,000", "$2,500", "appraisal receipts"]),
    ],
)
def test_retrieval_returns_right_section_and_citation(
    retriever: PolicyRetriever, query: str, expected_section: str, expected_fragments: list[str]
) -> None:
    top = retriever.search(query)[0]

    assert top.source == "sample_policy.md"
    assert top.section == expected_section
    assert top.citation == f"sample_policy.md — {expected_section}"
    for fragment in expected_fragments:
        assert fragment in top.text


def test_retrieval_respects_k_and_orders_by_relevance(retriever: PolicyRetriever) -> None:
    hits = retriever.search("pipe burst deductible", k=2)
    assert len(hits) == 2
    assert hits[0].distance <= hits[1].distance
    assert len(retriever.search("pipe burst deductible", k=1)) == 1


def test_blank_query_returns_nothing(retriever: PolicyRetriever) -> None:
    assert retriever.search("   ") == []


def test_ingestion_is_idempotent_across_restarts(tmp_path: Path, embedder: HashingEmbedder) -> None:
    chroma = tmp_path / "chroma"
    first = get_collection(chroma, "policy")
    assert ingest_policy(REAL_POLICY, first, embedder) == 2
    assert first.count() == 2

    # "Restart": brand-new client on the same persisted directory.
    second = get_collection(chroma, "policy")
    assert ingest_policy(REAL_POLICY, second, embedder) == 0  # nothing re-embedded
    ingest_policy(REAL_POLICY, second, embedder)
    assert second.count() == 2


def test_ingestion_updates_changed_and_removes_stale_sections(tmp_path: Path, embedder: HashingEmbedder) -> None:
    policy = tmp_path / "sample_policy.md"
    policy.write_text(REAL_POLICY.read_text())
    collection = get_collection(tmp_path / "chroma", "policy")
    ingest_policy(policy, collection, embedder)

    policy.write_text(
        "# T\n\n## Section 1: Home Water Damage Coverage\n\nCovered up to $30,000.\n"
    )
    assert ingest_policy(policy, collection, embedder) == 1
    stored = collection.get(include=["documents", "metadatas"])
    assert len(stored["ids"]) == 1  # Section 2 removed
    assert stored["documents"] == ["Covered up to $30,000."]


def test_irrelevant_query_is_far_away(retriever: PolicyRetriever) -> None:
    hits = retriever.search("quantum chromodynamics lattice")
    assert all(h.distance >= 0.95 for h in hits)


@pytest.mark.real_embeddings
def test_real_embedding_model_ranks_sections_correctly(tmp_path: Path) -> None:
    """Optional: exercises the real fastembed model (`pytest -m real_embeddings`, needs the model cached)."""
    from app.rag.embeddings import FastEmbedEmbedder

    emb = FastEmbedEmbedder("BAAI/bge-small-en-v1.5")
    collection = get_collection(tmp_path / "chroma", "policy_real")
    ingest_policy(REAL_POLICY, collection, emb)
    retriever = PolicyRetriever(collection, emb)

    assert retriever.search("Are burst pipes covered?")[0].section == SECTION_1
    assert retriever.search("What about gradual leaks or floods?")[0].section == SECTION_1
    assert retriever.search("Do I need receipts for my jewelry?")[0].section == SECTION_2

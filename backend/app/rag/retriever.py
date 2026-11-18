"""Top-k semantic retrieval over policy sections, returning citation-ready results."""

from __future__ import annotations

from dataclasses import dataclass

from chromadb.api.models.Collection import Collection

from app.rag.embeddings import Embedder


@dataclass(frozen=True)
class RetrievedSection:
    source: str
    section: str
    text: str
    distance: float

    @property
    def citation(self) -> str:
        return f"{self.source} — {self.section}"


class PolicyRetriever:
    def __init__(self, collection: Collection, embedder: Embedder, top_k: int = 3) -> None:
        self._collection = collection
        self._embedder = embedder
        self._top_k = top_k

    def search(self, query: str, k: int | None = None) -> list[RetrievedSection]:
        query = query.strip()
        count = self._collection.count()
        if not query or count == 0:
            return []
        result = self._collection.query(
            query_embeddings=[self._embedder.embed_query(query)],
            n_results=min(k or self._top_k, count),
            include=["documents", "metadatas", "distances"],
        )
        return [
            RetrievedSection(
                source=str(meta["source"]),
                section=str(meta["section"]),
                text=doc,
                distance=float(dist),
            )
            for doc, meta, dist in zip(
                result["documents"][0], result["metadatas"][0], result["distances"][0]
            )
        ]

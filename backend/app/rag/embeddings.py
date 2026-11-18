"""Embedding backends behind a tiny interface (swap-able and fakeable in tests)."""

from __future__ import annotations

from typing import Protocol


class Embedder(Protocol):
    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class FastEmbedEmbedder:
    """Local ONNX embeddings via fastembed (no PyTorch, no API key, works offline once cached)."""

    def __init__(self, model_name: str) -> None:
        from fastembed import TextEmbedding

        self._model = TextEmbedding(model_name=model_name)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [vec.tolist() for vec in self._model.embed(texts)]

    def embed_query(self, text: str) -> list[float]:
        return [vec.tolist() for vec in self._model.query_embed(text)][0]

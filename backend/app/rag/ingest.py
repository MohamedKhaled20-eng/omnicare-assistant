"""Policy ingestion: markdown -> section chunks -> idempotent upsert into Chroma."""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from pathlib import Path

import chromadb
from chromadb.api.models.Collection import Collection

from app.rag.embeddings import Embedder

logger = logging.getLogger(__name__)

_H1 = re.compile(r"^#\s+(.+?)\s*$")
_H2 = re.compile(r"^##\s+(.+?)\s*$")


@dataclass(frozen=True)
class PolicySection:
    source: str
    section: str
    text: str
    document_title: str = ""

    @property
    def chunk_id(self) -> str:
        return hashlib.sha256(f"{self.source}::{self.section}".encode()).hexdigest()[:24]

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(f"{self.document_title}\n{self.section}\n{self.text}".encode()).hexdigest()

    @property
    def embedding_text(self) -> str:
        """Heading is embedded with the body so title-like queries match their section."""
        return f"{self.section}\n{self.text}"


def parse_policy_sections(markdown: str, source: str) -> list[PolicySection]:
    """Split a markdown document into one chunk per `##` heading."""
    title = ""
    sections: list[PolicySection] = []
    heading: str | None = None
    body: list[str] = []

    def save_section() -> None:
        if heading is not None:
            text = "\n".join(body).strip()
            if text:
                sections.append(PolicySection(source, heading, text, title))

    for line in markdown.splitlines():
        if section_match := _H2.match(line):
            save_section()
            heading, body = section_match.group(1), []
        elif (title_match := _H1.match(line)) and not title:
            title = title_match.group(1)
        elif heading is not None:
            body.append(line)
    save_section()
    return sections


def get_collection(chroma_path: Path, name: str) -> Collection:
    chroma_path.mkdir(parents=True, exist_ok=True)
    chroma = chromadb.PersistentClient(path=str(chroma_path))
    return chroma.get_or_create_collection(name=name, metadata={"hnsw:space": "cosine"})


def ingest_policy(policy_path: Path, collection: Collection, embedder: Embedder) -> int:
    """Upsert policy sections; safe to run on every startup.

    Chunk ids are deterministic (source + section), unchanged chunks are not re-embedded,
    and chunks that disappeared from the source file are removed.
    Returns the number of chunks that were (re)written.
    """
    source = policy_path.name
    sections = parse_policy_sections(policy_path.read_text(encoding="utf-8"), source)

    existing = collection.get(where={"source": source}, include=["metadatas"])
    existing_hashes = {
        chunk_id: (metadata or {}).get("content_hash")
        for chunk_id, metadata in zip(existing["ids"], existing["metadatas"])
    }

    desired_ids = {section.chunk_id for section in sections}
    stale_ids = [chunk_id for chunk_id in existing_hashes if chunk_id not in desired_ids]
    if stale_ids:
        collection.delete(ids=stale_ids)

    changed_sections = [
        section for section in sections
        if existing_hashes.get(section.chunk_id) != section.content_hash
    ]
    if changed_sections:
        collection.upsert(
            ids=[section.chunk_id for section in changed_sections],
            documents=[section.text for section in changed_sections],
            embeddings=embedder.embed_documents(
                [section.embedding_text for section in changed_sections]
            ),
            metadatas=[
                {
                    "source": section.source,
                    "section": section.section,
                    "document_title": section.document_title,
                    "content_hash": section.content_hash,
                }
                for section in changed_sections
            ],
        )
    logger.info(
        "policy ingestion complete",
        extra={
            "source": source,
            "sections": len(sections),
            "written": len(changed_sections),
            "removed": len(stale_ids),
        },
    )
    return len(changed_sections)

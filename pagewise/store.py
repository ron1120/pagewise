"""The vector index: ChromaDB on disk, with swappable embeddings."""

from __future__ import annotations

import hashlib
import math
import re
from typing import Protocol

import chromadb

from .chunk import Chunk
from .config import COLLECTION


class Embedder(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class MiniLMEmbedder:
    """ChromaDB's default local model (all-MiniLM-L6-v2 via ONNX). No API key; downloads ~80 MB on first use."""

    def __init__(self) -> None:
        from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

        self._fn = DefaultEmbeddingFunction()

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[float(x) for x in v] for v in self._fn(texts)]


class HashEmbedder:
    """Tiny deterministic bag-of-words embedder for tests: no model download, similar words give similar vectors."""

    def __init__(self, dims: int = 256) -> None:
        self.dims = dims

    def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for text in texts:
            vec = [0.0] * self.dims
            for word in re.findall(r"[a-z0-9]+", text.lower()):
                vec[int(hashlib.md5(word.encode()).hexdigest(), 16) % self.dims] += 1.0
            norm = math.sqrt(sum(x * x for x in vec)) or 1.0
            out.append([x / norm for x in vec])
        return out


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0


class Index:
    def __init__(self, path: str, embedder: Embedder) -> None:
        self.embedder = embedder
        self._client = chromadb.PersistentClient(path=path)
        self._all: list[Chunk] | None = None

    def build(self, chunks: list[Chunk]) -> int:
        """Replace the whole collection with these chunks."""
        self._all = None
        try:
            self._client.delete_collection(COLLECTION)
        except Exception:
            pass
        col = self._client.create_collection(COLLECTION, metadata={"hnsw:space": "cosine"})
        for i in range(0, len(chunks), 64):
            batch = chunks[i : i + 64]
            col.add(
                ids=[c.id for c in batch],
                embeddings=self.embedder.embed([c.embed_text for c in batch]),
                documents=[c.embed_text for c in batch],
                metadatas=[c.to_meta() for c in batch],
            )
        return len(chunks)

    def _col(self):
        return self._client.get_collection(COLLECTION)

    def count(self) -> int:
        try:
            return self._col().count()
        except Exception:
            return 0

    def all_chunks(self) -> list[Chunk]:
        """Every chunk, for keyword ranking. Cached: a site is a few hundred chunks."""
        if self._all is None:
            got = self._col().get(include=["metadatas"])
            self._all = [Chunk.from_meta(i, m) for i, m in zip(got["ids"], got["metadatas"])]
        return self._all

    def search(self, question: str, n: int, extra_ids: tuple[str, ...] = ()) -> list[tuple[Chunk, float]]:
        """The n nearest chunks, plus the chunks named in extra_ids, each with its cosine similarity.

        extra_ids lets keyword search nominate chunks the vector search missed; their similarity is still computed
        exactly, so every candidate is scored the same way.
        """
        col = self._col()
        query = self.embedder.embed([question])[0]
        res = col.query(query_embeddings=[query], n_results=min(n, col.count()), include=["metadatas", "distances"])
        found = {
            id_: (Chunk.from_meta(id_, meta), 1.0 - dist)
            for id_, meta, dist in zip(res["ids"][0], res["metadatas"][0], res["distances"][0])
        }
        missing = [i for i in extra_ids if i not in found]
        if missing:
            got = col.get(ids=missing, include=["metadatas", "embeddings"])
            for id_, meta, emb in zip(got["ids"], got["metadatas"], got["embeddings"]):
                found[id_] = (Chunk.from_meta(id_, meta), _cosine(query, [float(x) for x in emb]))
        return list(found.values())

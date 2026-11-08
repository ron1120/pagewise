"""Glue between the crawl output on disk and the vector index."""

from __future__ import annotations

import json
import os

from .chunk import chunk_pages
from .config import INDEX_DIR, PAGES_FILE
from .crawl import Page
from .store import Embedder, Index, MiniLMEmbedder


def default_embedder() -> Embedder:
    # PAGEWISE_EMBEDDER=hash gives a tiny offline embedder, handy for CI and quick smoke tests.
    if os.environ.get("PAGEWISE_EMBEDDER") == "hash":
        from .store import HashEmbedder

        return HashEmbedder()
    return MiniLMEmbedder()


def save_pages(pages: list[Page], path: str = PAGES_FILE) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump([p.to_dict() for p in pages], f, indent=2, ensure_ascii=False)
        f.write("\n")


def load_pages(path: str = PAGES_FILE) -> list[Page]:
    with open(path, encoding="utf-8") as f:
        return [Page.from_dict(d) for d in json.load(f)]


def build_index(pages: list[Page], index_dir: str = INDEX_DIR, embedder: Embedder | None = None) -> Index:
    index = Index(index_dir, embedder or default_embedder())
    index.build(chunk_pages(pages))
    return index


def open_index(index_dir: str = INDEX_DIR, embedder: Embedder | None = None) -> Index:
    index = Index(index_dir, embedder or default_embedder())
    if index.count() == 0:
        raise SystemExit("No index found. Run `pagewise crawl <url>` and then `pagewise index` first.")
    return index

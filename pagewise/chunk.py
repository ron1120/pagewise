"""Split pages into small, citable chunks. Each chunk remembers its page URL, title and heading."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from .config import CHUNK_CHARS
from .crawl import Page


@dataclass
class Chunk:
    id: str
    url: str
    title: str
    heading: str
    text: str

    @property
    def embed_text(self) -> str:
        """What gets embedded: the text plus where it came from, so 'Where it stands' means something."""
        return f"{self.title} > {self.heading}\n{self.text}"

    def to_meta(self) -> dict:
        return {"url": self.url, "title": self.title, "heading": self.heading, "text": self.text}

    @classmethod
    def from_meta(cls, id: str, meta: dict) -> "Chunk":
        return cls(id, meta["url"], meta["title"], meta["heading"], meta["text"])


def _chunk_id(url: str, n: int) -> str:
    return hashlib.sha1(f"{url}#{n}".encode()).hexdigest()[:12]


def chunk_page(page: Page, max_chars: int = CHUNK_CHARS) -> list[Chunk]:
    """Group consecutive paragraphs under the same heading until a chunk is about max_chars long."""
    chunks: list[Chunk] = []
    buf: list[str] = []
    heading = None

    def flush() -> None:
        if buf:
            chunks.append(Chunk(_chunk_id(page.url, len(chunks)), page.url, page.title, heading, " ".join(buf)))
            buf.clear()

    for section_heading, text in page.sections:
        if section_heading != heading or sum(len(b) for b in buf) + len(text) > max_chars:
            flush()
            heading = section_heading
        buf.append(text)
    flush()
    return chunks


def chunk_pages(pages: list[Page], max_chars: int = CHUNK_CHARS) -> list[Chunk]:
    return [c for page in pages for c in chunk_page(page, max_chars)]

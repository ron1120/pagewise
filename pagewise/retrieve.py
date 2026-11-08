"""Hybrid retrieval: vector search first, then a keyword-overlap blend so exact names and terms still win."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .chunk import Chunk
from .config import CANDIDATES, MIN_SCORE, TOP_K, VECTOR_WEIGHT
from .store import Index

_STOPWORDS = set(
    "a an and are as at be been but by can could did do does for from had has have how i if in into is it its "
    "me my of on or our so than that the their them then there these they this to was we were what when where "
    "which who why will with would you your about tell".split()
)


@dataclass
class Hit:
    chunk: Chunk
    score: float
    vector: float
    keywords: float


def _singular(word: str) -> str:
    """Plain plural stripping, so 'creates' matches 'create' and 'endpoints' matches 'endpoint'."""
    if len(word) <= 3 or not word.isalpha():
        return word
    if word.endswith("ies"):
        return word[:-3] + "y"
    if word.endswith(("xes", "zes", "ches", "shes", "sses")):
        return word[:-2]
    if word.endswith("s") and not word.endswith(("ss", "us", "is")):
        return word[:-1]
    return word


def tokens(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9][a-z0-9+#.-]*", text.lower())
    return {_singular(w) for w in words if w not in _STOPWORDS and len(w) > 1}


def _keyword_score(query_tokens: set[str], chunk: Chunk) -> float:
    if not query_tokens:
        return 0.0
    haystack = tokens(f"{chunk.title} {chunk.heading} {chunk.text}")
    return len(query_tokens & haystack) / len(query_tokens)


def retrieve(index: Index, question: str, k: int = TOP_K, candidates: int = CANDIDATES) -> list[Hit]:
    """Top-k chunks for the question, best first, each with its blended score.

    Candidates come from two searches: the nearest chunks by meaning (vectors) and the best matches by exact
    words (keywords). Both lists are then scored the same way and blended.
    """
    query_tokens = tokens(question)
    by_keywords = sorted(index.all_chunks(), key=lambda c: _keyword_score(query_tokens, c), reverse=True)
    keyword_ids = tuple(c.id for c in by_keywords[:candidates] if _keyword_score(query_tokens, c) > 0)
    hits = []
    for chunk, vector in index.search(question, candidates, keyword_ids):
        keywords = _keyword_score(query_tokens, chunk)
        hits.append(Hit(chunk, VECTOR_WEIGHT * vector + (1 - VECTOR_WEIGHT) * keywords, vector, keywords))
    hits.sort(key=lambda h: h.score, reverse=True)
    return hits[:k]


def is_covered(hits: list[Hit], min_score: float = MIN_SCORE) -> bool:
    """False when even the best chunk is too weak to answer from: the model is never called in that case."""
    return bool(hits) and hits[0].score >= min_score

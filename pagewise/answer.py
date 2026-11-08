"""The whole question-to-answer pipeline, with the checks that keep it from guessing."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

from .config import MAX_QUESTION_CHARS, MIN_SCORE
from .llm import Judge, ModelUnavailable
from .retrieve import Hit, is_covered, retrieve
from .store import Index

NOT_COVERED = "I can't answer that from this site's pages."
NEEDS_REVIEW = "I couldn't produce a reliable answer to that. Please look at the site directly."

ANSWERED = "answered"
NOT_COVERED_STATUS = "not_covered"
NEEDS_REVIEW_STATUS = "needs_review"


@dataclass
class Source:
    n: int
    url: str
    title: str
    heading: str
    excerpt: str


@dataclass
class Answer:
    question: str
    status: str
    text: str
    sources: list[Source] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _numbers(text: str) -> set[str]:
    return {n.replace(",", "").rstrip(".") for n in re.findall(r"\d[\d,]*(?:\.\d+)?", text)}


def unsupported_numbers(answer: str, cited: list[Hit]) -> set[str]:
    """Numbers the answer states that none of the cited sources contain."""
    allowed = set().union(*(_numbers(h.chunk.text + " " + h.chunk.title) for h in cited)) if cited else set()
    return _numbers(answer) - allowed


def _source(n: int, hit: Hit) -> Source:
    excerpt = hit.chunk.text if len(hit.chunk.text) <= 280 else hit.chunk.text[:277].rstrip() + "..."
    return Source(n, hit.chunk.url, hit.chunk.title, hit.chunk.heading, excerpt)


def ask(question: str, index: Index, judge: Judge, min_score: float = MIN_SCORE) -> Answer:
    question = " ".join(question.split())
    if not question:
        raise ValueError("The question is empty.")
    if len(question) > MAX_QUESTION_CHARS:
        raise ValueError(f"The question is longer than {MAX_QUESTION_CHARS} characters.")

    hits = retrieve(index, question)
    # Nothing relevant on the site: refuse without calling the model at all.
    if not is_covered(hits, min_score):
        return Answer(question, NOT_COVERED_STATUS, NOT_COVERED)

    try:
        verdict = judge.judge(question, hits)
    except ModelUnavailable:
        return Answer(question, NEEDS_REVIEW_STATUS, NEEDS_REVIEW)

    if not verdict["answerable"] or not verdict["answer"].strip():
        return Answer(question, NOT_COVERED_STATUS, NOT_COVERED)

    # The model must cite real sources it was shown, and may not introduce numbers the sources do not contain.
    ids = sorted(set(verdict["source_ids"]))
    if not ids or any(i < 1 or i > len(hits) for i in ids):
        return Answer(question, NEEDS_REVIEW_STATUS, NEEDS_REVIEW)
    cited = [hits[i - 1] for i in ids]
    if unsupported_numbers(verdict["answer"], cited):
        return Answer(question, NEEDS_REVIEW_STATUS, NEEDS_REVIEW)

    return Answer(question, ANSWERED, verdict["answer"].strip(), [_source(i, hits[i - 1]) for i in ids])

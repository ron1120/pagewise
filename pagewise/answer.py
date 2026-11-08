"""The whole question-to-answer pipeline, with the checks that keep it from guessing."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

from .config import MAX_QUESTION_CHARS, MIN_SCORE, SOURCE_NAME
from .llm import Judge, ModelUnavailable
from .retrieve import Hit, is_covered, retrieve
from .store import Index

NOT_COVERED = f"I can't answer that from {SOURCE_NAME}."
NEEDS_REVIEW = "I couldn't produce a reliable answer to that. Please check the source directly."

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


def _problem(verdict: dict, hits: list[Hit]) -> str | None:
    """What is wrong with a verdict, worded as feedback for the model, or None when it is acceptable."""
    ids = sorted(set(verdict["source_ids"]))
    if not ids or any(i < 1 or i > len(hits) for i in ids):
        return f"Your answer must cite at least one source id between 1 and {len(hits)}; yours cited {verdict['source_ids']}."
    bad = unsupported_numbers(verdict["answer"], [hits[i - 1] for i in ids])
    if bad:
        return (
            f"Your answer states {sorted(bad)}, which none of the sources you cited contain. "
            "Rewrite it using only facts that appear in the sources."
        )
    return None


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
    # If it slips, it gets exactly one chance to correct itself; a second slip is shown as "couldn't answer".
    problem = _problem(verdict, hits)
    if problem:
        try:
            verdict = judge.judge(question, hits, correction=problem)
        except ModelUnavailable:
            return Answer(question, NEEDS_REVIEW_STATUS, NEEDS_REVIEW)
        if not verdict["answerable"] or not verdict["answer"].strip():
            return Answer(question, NOT_COVERED_STATUS, NOT_COVERED)
        if _problem(verdict, hits):
            return Answer(question, NEEDS_REVIEW_STATUS, NEEDS_REVIEW)

    ids = sorted(set(verdict["source_ids"]))
    return Answer(question, ANSWERED, verdict["answer"].strip(), [_source(i, hits[i - 1]) for i in ids])

"""Golden-question evaluation.

Two modes:
  offline  retrieval only, no API key: is the right page found, and does the not-covered gate fire on off-topic questions?
  live     the full pipeline with Claude: right status, right page cited, expected facts present, refusals honoured.

Each case in the golden file looks like:
  {"question": "...", "expect": "answer" | "refuse",
   "pages": ["/work/vera/"],            # the path of a retrieved/cited source must be one of these (answer cases)
   "contains": ["12 of 12"],            # live only: the answer must mention these (case-insensitive)
   "refused_by": "gate" | "model"}      # refuse cases: "gate" = off-topic, caught before the model; "model" = on-topic but absent
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.parse import urlparse

from .answer import ANSWERED, ask
from .config import MIN_SCORE
from .llm import Judge
from .retrieve import is_covered, retrieve
from .store import Index


@dataclass
class Result:
    question: str
    ok: bool
    detail: str
    calls: int = 0  # model calls this question needed (live mode)
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float | None = 0.0  # None when the model's price is unknown


def _path(url: str) -> str:
    return urlparse(url).path or "/"


def load_golden(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _offline(case: dict, index: Index, min_score: float) -> Result:
    hits = retrieve(index, case["question"])
    covered = is_covered(hits, min_score)
    best = hits[0].score if hits else 0.0
    if case["expect"] == "refuse":
        if case.get("refused_by") == "model":
            return Result(case["question"], True, f"skipped offline (needs the model), best score {best:.2f}")
        return Result(case["question"], not covered, f"gate {'fired' if not covered else 'did NOT fire'}, best score {best:.2f}")
    found = any(_path(h.chunk.url) in case["pages"] for h in hits)
    return Result(case["question"], found and covered, f"page {'found' if found else 'MISSING'} in top {len(hits)}, best score {best:.2f}")


def _live(case: dict, index: Index, judge: Judge, min_score: float) -> Result:
    answer = ask(case["question"], index, judge, min_score)
    usage = {
        "calls": answer.usage["calls"], "input_tokens": answer.usage["input_tokens"],
        "output_tokens": answer.usage["output_tokens"], "cost_usd": answer.cost_usd,
    }
    if case["expect"] == "refuse":
        return Result(case["question"], answer.status != ANSWERED, f"status {answer.status}", **usage)
    if answer.status != ANSWERED:
        return Result(case["question"], False, f"expected an answer, got {answer.status}", **usage)
    cited = any(_path(s.url) in case["pages"] for s in answer.sources)
    missing = [c for c in case.get("contains", []) if c.lower() not in answer.text.lower()]
    ok = cited and not missing
    return Result(case["question"], ok, f"cited expected page: {cited}; missing facts: {missing or 'none'}", **usage)


def run_evals(golden: list[dict], index: Index, judge: Judge | None = None, min_score: float = MIN_SCORE) -> list[Result]:
    return [
        _live(c, index, judge, min_score) if judge is not None else _offline(c, index, min_score)
        for c in golden
    ]


def cost_summary(results: list[Result]) -> str | None:
    """One line on what a live run cost, or None for an offline run (no model calls were made)."""
    called = [r for r in results if r.calls]
    if not called:
        return None
    tokens_in, tokens_out = sum(r.input_tokens for r in results), sum(r.output_tokens for r in results)
    base = f"Model calls: {sum(r.calls for r in results)} for {len(called)} of {len(results)} questions " \
           f"({len(results) - len(called)} refused before the model, free). Tokens: {tokens_in} in, {tokens_out} out."
    if any(r.cost_usd is None for r in results):
        return base + " Cost: unknown (this model is not in PRICES in pagewise/config.py)."
    total = sum(r.cost_usd for r in results)
    return base + f" Estimated cost: ${total:.4f} total, ${total / len(called):.4f} per answered question."


def report(results: list[Result]) -> int:
    for r in results:
        print(f"{'PASS' if r.ok else 'FAIL'}  {r.question}\n      {r.detail}")
    passed = sum(r.ok for r in results)
    print(f"\n{passed}/{len(results)} passed")
    summary = cost_summary(results)
    if summary:
        print(summary)
    return 0 if passed == len(results) else 1

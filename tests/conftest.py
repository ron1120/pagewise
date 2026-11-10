"""Shared fixtures: a tiny fictional bakery site, a hash embedder (no model download) and a scripted fake model."""

from __future__ import annotations

import pytest

from pagewise.build import build_index
from pagewise.crawl import Page
from pagewise.llm import ModelUnavailable
from pagewise.store import HashEmbedder

PAGES = [
    Page(
        "https://bakery.test/",
        "Rye & Co Bakery",
        [
            ("Rye & Co Bakery", "A neighbourhood bakery in Haifa, baking sourdough bread every morning since 2014."),
            ("Opening hours", "We are open Sunday to Friday from 7am to 4pm. We are closed on Saturdays."),
        ],
    ),
    Page(
        "https://bakery.test/menu/",
        "Menu | Rye & Co Bakery",
        [
            ("Breads", "Sourdough loaf costs 28 shekels. Rye loaf costs 32 shekels. Challah is baked on Fridays."),
            ("Pastries", "Almond croissant costs 14 shekels. Cheese bourekas cost 9 shekels."),
        ],
    ),
    Page(
        "https://bakery.test/contact/",
        "Contact | Rye & Co Bakery",
        [("Find us", "Visit us at 12 Herzl Street, Haifa, or call the shop on 04-555-0100 to place a bulk order.")],
    ),
]


@pytest.fixture
def index(tmp_path):
    return build_index(PAGES, str(tmp_path / "index"), HashEmbedder())


class ScriptedJudge:
    """Returns canned verdicts (one, or a list used in order), or raises ModelUnavailable. Records every call.

    Give it a `model` name to have costs priced, and `usage` for the tokens each call reports.
    """

    def __init__(self, verdict=None, error: bool = False, model: str | None = None, usage: dict | None = None) -> None:
        self.verdicts = verdict if isinstance(verdict, list) else [verdict]
        self.error, self.calls, self.model, self.usage = error, [], model, usage

    def judge(self, question, hits, correction=None):
        self.calls.append((question, hits, correction))
        if self.error:
            raise ModelUnavailable("scripted failure", self.usage)
        verdict = self.verdicts[min(len(self.calls) - 1, len(self.verdicts) - 1)]
        return {**verdict, "usage": self.usage} if self.usage is not None else verdict

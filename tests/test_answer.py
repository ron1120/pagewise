import pytest
from conftest import ScriptedJudge

from pagewise.answer import ANSWERED, NEEDS_REVIEW_STATUS, NOT_COVERED_STATUS, ask, unsupported_numbers
from pagewise.config import MAX_QUESTION_CHARS


def good(answer="A sourdough loaf costs 28 shekels.", ids=(1,)):
    return {"answerable": True, "answer": answer, "source_ids": list(ids)}


def test_off_topic_question_is_refused_without_calling_the_model(index):
    judge = ScriptedJudge(good())
    result = ask("Who won the football world cup in 2022?", index, judge)
    assert result.status == NOT_COVERED_STATUS and result.sources == []
    assert judge.calls == []  # the model is never even asked


def test_a_supported_answer_comes_back_with_its_sources(index):
    result = ask("How much does the sourdough loaf cost?", index, ScriptedJudge(good()))
    assert result.status == ANSWERED
    assert result.text == "A sourdough loaf costs 28 shekels."
    assert [s.url for s in result.sources] == ["https://bakery.test/menu/"] and result.sources[0].n == 1


def test_the_model_saying_it_cannot_answer_is_respected(index):
    verdict = {"answerable": False, "answer": "", "source_ids": []}
    assert ask("How much does the sourdough loaf cost?", index, ScriptedJudge(verdict)).status == NOT_COVERED_STATUS


@pytest.mark.parametrize("ids", [[], [0], [99]])
def test_answers_citing_nothing_or_unknown_sources_are_rejected(index, ids):
    result = ask("How much does the sourdough loaf cost?", index, ScriptedJudge(good(ids=ids)))
    assert result.status == NEEDS_REVIEW_STATUS and result.sources == []


def test_a_number_the_sources_do_not_contain_is_rejected(index):
    invented = good("A sourdough loaf costs 35 shekels.")
    assert ask("How much does the sourdough loaf cost?", index, ScriptedJudge(invented)).status == NEEDS_REVIEW_STATUS


def test_numbers_are_compared_without_thousands_separators_or_trailing_dots():
    from pagewise.chunk import Chunk
    from pagewise.retrieve import Hit

    hit = Hit(Chunk("a", "u", "t", "h", "We sold 12,000 loaves in 2024."), 1.0, 1.0, 1.0)
    assert unsupported_numbers("We sold 12000 loaves in 2024.", [hit]) == set()
    assert unsupported_numbers("We sold 13000 loaves.", [hit]) == {"13000"}


def test_a_model_failure_becomes_a_visible_needs_review_not_silence(index):
    result = ask("How much does the sourdough loaf cost?", index, ScriptedJudge(error=True))
    assert result.status == NEEDS_REVIEW_STATUS and result.text


def test_bad_questions_are_rejected_before_anything_runs(index):
    judge = ScriptedJudge(good())
    with pytest.raises(ValueError):
        ask("   ", index, judge)
    with pytest.raises(ValueError):
        ask("x" * (MAX_QUESTION_CHARS + 1), index, judge)
    assert judge.calls == []


def test_whitespace_in_questions_is_normalised(index):
    judge = ScriptedJudge(good())
    ask("How   much\n does the sourdough loaf   cost?", index, judge)
    assert judge.calls[0][0] == "How much does the sourdough loaf cost?"


def test_refusals_name_the_configured_source(monkeypatch):
    import importlib

    import pagewise.answer as answer_module

    monkeypatch.setenv("PAGEWISE_SOURCE_NAME", "the project docs")
    import pagewise.config as config

    importlib.reload(config)
    importlib.reload(answer_module)
    try:
        assert answer_module.NOT_COVERED == "I can't answer that from the project docs."
    finally:
        monkeypatch.delenv("PAGEWISE_SOURCE_NAME")
        importlib.reload(config)
        importlib.reload(answer_module)

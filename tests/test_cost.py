import pytest
from conftest import ScriptedJudge

from pagewise.answer import ANSWERED, NEEDS_REVIEW_STATUS, NOT_COVERED_STATUS, ask
from pagewise.config import PRICES, cost_usd
from pagewise.evals import Result, cost_summary, report, run_evals

TOKENS = {"input_tokens": 2000, "output_tokens": 100}


def good(answer="A sourdough loaf costs 28 shekels.", ids=(1,)):
    return {"answerable": True, "answer": answer, "source_ids": list(ids)}


def test_cost_is_tokens_times_the_models_per_million_price():
    assert cost_usd("claude-sonnet-5-5", 1_000_000, 0) == 2.00
    assert cost_usd("claude-sonnet-5-5", 0, 1_000_000) == 10.00
    assert cost_usd("claude-opus-5-5", 2000, 100) == pytest.approx(2000 * 4 / 1e6 + 100 * 20 / 1e6)
    assert cost_usd("some-future-model", 5, 5) is None and cost_usd(None, 5, 5) is None
    assert all(inp > 0 and out > inp for inp, out in PRICES.values())  # output always costs more than input


def test_an_answer_reports_its_calls_tokens_and_cost(index):
    judge = ScriptedJudge(good(), model="claude-sonnet-5-5", usage=TOKENS)
    result = ask("How much does the sourdough loaf cost?", index, judge)
    assert result.status == ANSWERED
    assert result.usage == {"calls": 1, "input_tokens": 2000, "output_tokens": 100}
    assert result.cost_usd == pytest.approx(2000 * 2 / 1e6 + 100 * 10 / 1e6)
    assert result.to_dict()["usage"]["calls"] == 1 and result.to_dict()["cost_usd"] > 0


def test_a_corrective_retry_adds_the_second_call_to_the_cost(index):
    judge = ScriptedJudge([good("It costs 35 shekels."), good()], model="claude-sonnet-5-5", usage=TOKENS)
    result = ask("How much does the sourdough loaf cost?", index, judge)
    assert result.status == ANSWERED and result.usage == {"calls": 2, "input_tokens": 4000, "output_tokens": 200}
    assert result.cost_usd == pytest.approx(2 * (2000 * 2 / 1e6 + 100 * 10 / 1e6))


def test_a_question_refused_before_the_model_costs_nothing(index):
    judge = ScriptedJudge(good(), model="claude-sonnet-5-5", usage=TOKENS)
    result = ask("Who won the football world cup in 2022?", index, judge)
    assert result.status == NOT_COVERED_STATUS and result.cost_usd == 0.0 and judge.calls == []
    assert result.usage == {"calls": 0, "input_tokens": 0, "output_tokens": 0}


def test_a_failed_call_is_still_paid_for(index):
    judge = ScriptedJudge(error=True, model="claude-sonnet-5-5", usage=TOKENS)
    result = ask("How much does the sourdough loaf cost?", index, judge)
    assert result.status == NEEDS_REVIEW_STATUS and result.usage["calls"] == 1 and result.cost_usd > 0


def test_an_unpriced_model_gives_no_dollar_figure_but_keeps_the_tokens(index):
    result = ask("How much does the sourdough loaf cost?", index, ScriptedJudge(good(), model="mystery-model", usage=TOKENS))
    assert result.cost_usd is None and result.usage["input_tokens"] == 2000


def test_the_live_eval_summarises_cost_and_ignores_free_refusals(index):
    judge = ScriptedJudge(good(), model="claude-sonnet-5-5", usage=TOKENS)
    golden = [
        {"question": "How much does the sourdough loaf cost?", "expect": "answer", "pages": ["/menu/"], "contains": ["28"]},
        {"question": "Who won the football world cup in 2022?", "expect": "refuse", "refused_by": "gate"},
    ]
    results = run_evals(golden, index, judge)
    summary = cost_summary(results)
    assert "Model calls: 1 for 1 of 2 questions (1 refused before the model, free)" in summary
    assert "Tokens: 2000 in, 100 out" in summary and "$0.0050 total, $0.0050 per answered question" in summary


def test_an_offline_eval_has_no_cost_line_and_unknown_prices_are_said_so(index, capsys):
    assert cost_summary(run_evals([{"question": "When are you open?", "expect": "answer", "pages": ["/"]}], index)) is None
    unpriced = [Result("q", True, "d", calls=1, input_tokens=5, output_tokens=5, cost_usd=None)]
    assert "unknown" in cost_summary(unpriced)
    report(unpriced)
    assert "Estimated cost" not in capsys.readouterr().out

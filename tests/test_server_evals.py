from pathlib import Path

from conftest import ScriptedJudge
from fastapi.testclient import TestClient

from pagewise.evals import run_evals
from pagewise.server import WEB_DIR, create_app


def client(index, judge=None, rate_limit=10):
    judge = judge or ScriptedJudge({"answerable": True, "answer": "28 shekels.", "source_ids": [1]})
    return TestClient(create_app(index, judge, rate_limit=rate_limit))


def test_health_and_home_page(index):
    c = client(index)
    assert c.get("/api/health").json() == {"status": "ok", "chunks": index.count()}
    assert "Ask this site" in c.get("/").text


def test_ask_returns_the_answer_and_its_sources(index):
    body = client(index).post("/api/ask", json={"question": "How much does the sourdough loaf cost?"}).json()
    assert body["status"] == "answered" and body["sources"][0]["url"] == "https://bakery.test/menu/"


def test_off_topic_question_is_refused_over_http_too(index):
    body = client(index).post("/api/ask", json={"question": "Who won the football world cup in 2022?"}).json()
    assert body["status"] == "not_covered" and body["sources"] == []


def test_invalid_questions_get_422(index):
    c = client(index)
    assert c.post("/api/ask", json={"question": ""}).status_code == 422
    assert c.post("/api/ask", json={"question": "x" * 501}).status_code == 422
    assert c.post("/api/ask", json={}).status_code == 422


def test_each_client_is_rate_limited(index):
    c = client(index, rate_limit=2)
    codes = [c.post("/api/ask", json={"question": "When are you open?"}).status_code for _ in range(3)]
    assert codes == [200, 200, 429]


def test_the_chat_page_never_inserts_answers_as_html():
    page = (Path(WEB_DIR) / "index.html").read_text()
    assert "innerHTML" not in page and "textContent" in page


def test_offline_evals_check_retrieval_and_the_gate(index):
    golden = [
        {"question": "How much does the sourdough loaf cost?", "expect": "answer", "pages": ["/menu/"]},
        {"question": "Who won the football world cup in 2022?", "expect": "refuse", "refused_by": "gate"},
        {"question": "What is the owner's salary?", "expect": "refuse", "refused_by": "model"},
        {"question": "How much does the sourdough loaf cost?", "expect": "answer", "pages": ["/no-such-page/"]},
    ]
    results = run_evals(golden, index)
    assert [r.ok for r in results] == [True, True, True, False]


def test_live_evals_check_citations_and_facts(index):
    judge = ScriptedJudge({"answerable": True, "answer": "A sourdough loaf costs 28 shekels.", "source_ids": [1]})
    golden = [
        {"question": "How much does the sourdough loaf cost?", "expect": "answer", "pages": ["/menu/"], "contains": ["28 shekels"]},
        {"question": "How much does the sourdough loaf cost?", "expect": "answer", "pages": ["/menu/"], "contains": ["35"]},
        {"question": "How much does the sourdough loaf cost?", "expect": "refuse"},
    ]
    assert [r.ok for r in run_evals(golden, index, judge)] == [True, False, False]


def test_the_home_page_injects_example_questions_safely(index, monkeypatch):
    from pagewise import server

    monkeypatch.setattr(server, "EXAMPLES", ["Where is it?", "</script><b>x</b>"])
    page = client(index).get("/").text
    assert "__EXAMPLES__" not in page and "Where is it?" in page and "</script><b>" not in page
    assert 'fetch("api/ask"' in page  # relative, so it works behind a proxy path like /assistant/

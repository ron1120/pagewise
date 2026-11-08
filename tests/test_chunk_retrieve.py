from conftest import PAGES

from pagewise.chunk import chunk_page, chunk_pages
from pagewise.crawl import Page
from pagewise.retrieve import is_covered, retrieve, tokens


def test_chunks_split_on_heading_changes_and_keep_their_source():
    chunks = chunk_page(PAGES[1])
    assert [c.heading for c in chunks] == ["Breads", "Pastries"]
    assert all(c.url == "https://bakery.test/menu/" and c.title.startswith("Menu") for c in chunks)


def test_chunks_respect_the_size_limit_and_have_stable_unique_ids():
    page = Page("u", "t", [("h", "x" * 400), ("h", "y" * 400), ("h", "z" * 400)])
    chunks = chunk_page(page, max_chars=900)
    assert [len(c.text) for c in chunks] == [801, 400]  # two paragraphs and a space, then the rest
    ids = [c.id for c in chunk_pages(PAGES)]
    assert len(ids) == len(set(ids)) and ids == [c.id for c in chunk_pages(PAGES)]


def test_tokens_drop_stopwords():
    assert tokens("What are the opening hours?") == {"opening", "hours"}


def test_retrieval_finds_the_right_page(index):
    hits = retrieve(index, "How much does the sourdough loaf cost?")
    assert hits[0].chunk.url == "https://bakery.test/menu/"
    assert hits == sorted(hits, key=lambda h: h.score, reverse=True)


def test_keyword_search_rescues_exact_terms_the_vectors_miss(index):
    # The phone number sits in a chunk about "finding us"; an exact term still surfaces it.
    hits = retrieve(index, "04-555-0100", k=3, candidates=1)
    assert any("04-555-0100" in h.chunk.text for h in hits)


def test_off_topic_questions_are_not_covered(index):
    assert not is_covered(retrieve(index, "Who won the football world cup in 2022?"))
    assert is_covered(retrieve(index, "When are you open?"))

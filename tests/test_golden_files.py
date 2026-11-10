import glob
import json

import pytest

FILES = sorted(glob.glob("evals/golden*.json"))


def test_golden_files_exist():
    assert any(f.endswith("golden.json") for f in FILES) and any(f.endswith("golden_argocd.json") for f in FILES)


@pytest.mark.parametrize("path", FILES)
def test_every_golden_case_is_well_formed(path):
    cases = json.load(open(path, encoding="utf-8"))
    assert cases and len({c["question"] for c in cases}) == len(cases), "duplicate questions"
    for c in cases:
        assert 0 < len(c["question"]) <= 500
        assert c["expect"] in ("answer", "refuse")
        if c["expect"] == "answer":
            assert c["pages"] and all(p.startswith("/") for p in c["pages"]), c["question"]
            assert all(isinstance(x, str) and x for x in c.get("contains", [])), c["question"]
        else:
            assert c["refused_by"] in ("gate", "model"), c["question"]


@pytest.mark.parametrize("path", FILES)
def test_each_golden_file_covers_answers_and_both_kinds_of_refusal(path):
    cases = json.load(open(path, encoding="utf-8"))
    kinds = {("answer" if c["expect"] == "answer" else c["refused_by"]) for c in cases}
    assert kinds == {"answer", "gate", "model"}

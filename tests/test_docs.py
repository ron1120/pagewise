import os

from pagewise.docs import load_docs, parse_markdown

MD = """# Task Manager

Intro line one
continues here.

## Auth model

1. POST /api/auth/register
2. POST /api/auth/login

```bash
curl -X POST http://localhost:8000/api/auth/login

echo done
```

| Route | Needs token |
|---|---|
| GET /health | no |

<!-- hidden note -->
### Details
Last words.
"""


def test_markdown_becomes_sections_under_their_headings():
    page = parse_markdown("https://x.test/README.md", MD, "README.md")
    assert page.title == "Task Manager"
    headings = [h for h, _ in page.sections]
    assert headings == ["Task Manager", "Auth model", "Auth model", "Auth model", "Details"]
    assert page.sections[0][1] == "Intro line one\ncontinues here."
    assert page.sections[1][1].startswith("1. POST /api/auth/register")
    assert "hidden note" not in " ".join(t for _, t in page.sections)


def test_code_blocks_keep_their_lines_and_blank_lines():
    page = parse_markdown("u", MD, "f")
    code = next(t for _, t in page.sections if t.startswith("```"))
    assert code == "```bash\ncurl -X POST http://localhost:8000/api/auth/login\n\necho done\n```"


def test_tables_stay_together_as_one_section():
    page = parse_markdown("u", MD, "f")
    assert any(t.startswith("| Route | Needs token |") and "GET /health" in t for _, t in page.sections)


def test_a_file_without_a_title_uses_its_path(tmp_path):
    assert parse_markdown("u", "just text", "notes/a.md").title == "notes/a.md"


def test_load_docs_builds_urls_from_the_base_url_and_skips_junk(tmp_path):
    (tmp_path / "README.md").write_text("# Top\ntext")
    (tmp_path / "ansible").mkdir()
    (tmp_path / "ansible" / "README.md").write_text("# Ansible\nplaybooks")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "x.md").write_text("# Junk\nignored")
    (tmp_path / "empty.md").write_text("")
    (tmp_path / "notes.txt").write_text("not markdown")
    pages = load_docs(str(tmp_path), "https://github.com/me/repo/blob/main/")
    assert [p.url for p in pages] == [
        "https://github.com/me/repo/blob/main/README.md",
        "https://github.com/me/repo/blob/main/ansible/README.md",
    ]

import os

from pagewise.docs import code_windows, load_docs, load_repo, parse_markdown

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


def _project(tmp_path):
    (tmp_path / "README.md").write_text("# App\nreadme text")
    (tmp_path / "main.py").write_text("print('hello')\n")
    (tmp_path / "Dockerfile").write_text("FROM python:3.12\n")
    (tmp_path / "compose.yml").write_text("services:\n  web:\n    ports: ['8000:8000']\n")
    (tmp_path / "env.example").write_text("SECRET_KEY=change-me\n")
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / ".github" / "workflows" / "ci.yml").write_text("on: push\n")
    # none of these may ever be read
    (tmp_path / ".env").write_text("ANTHROPIC_API_KEY=real-secret-value\n")
    (tmp_path / "server.pem").write_text("-----BEGIN PRIVATE KEY-----")
    (tmp_path / "prod.tfvars").write_text("db_password = \"hunter2\"\n")
    (tmp_path / "terraform.tfstate").write_text("{}")
    (tmp_path / "package-lock.json").write_text("{}")
    (tmp_path / "notes.txt").write_text("plain text file")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config.py").write_text("x = 1")
    return tmp_path


def test_without_include_code_only_markdown_is_read(tmp_path):
    pages = load_repo(str(_project(tmp_path)), "https://h/blob/main", include_code=False)
    assert [p.url for p in pages] == ["https://h/blob/main/README.md"]


def test_with_include_code_config_and_code_are_read_with_line_anchored_urls(tmp_path):
    pages = load_repo(str(_project(tmp_path)), "https://h/blob/main", include_code=True)
    urls = sorted(p.url for p in pages)
    assert urls == [
        "https://h/blob/main/.github/workflows/ci.yml#L1-L1",
        "https://h/blob/main/Dockerfile#L1-L1",
        "https://h/blob/main/README.md",
        "https://h/blob/main/compose.yml#L1-L3",
        "https://h/blob/main/env.example#L1-L1",
        "https://h/blob/main/main.py#L1-L1",
    ]


def test_secrets_and_junk_are_never_read(tmp_path):
    pages = load_repo(str(_project(tmp_path)), "https://h/blob/main", include_code=True)
    everything = " ".join(t for p in pages for _, t in p.sections) + " ".join(p.url for p in pages)
    for forbidden in ["real-secret-value", "PRIVATE KEY", "hunter2", "tfstate", "package-lock", "plain text file", ".env"]:
        assert forbidden not in everything


def test_code_files_are_split_into_windows_that_cover_every_line():
    text = "\n".join(f"line {n}" for n in range(1, 101))
    pages = code_windows("https://h/f.py", "f.py", text)
    assert len(pages) > 1
    spans = [p.sections[0][0] for p in pages]
    assert spans[0] == "lines 1-" + spans[0].split("-")[1] and pages[0].url.endswith("#L1-L" + spans[0].split("-")[1])
    covered = sum(int(s.split(" ")[1].split("-")[1]) - int(s.split(" ")[1].split("-")[0]) + 1 for s in spans)
    assert covered == 100 and all(p.title == "f.py" for p in pages)

"""Read a folder of Markdown files as if it were a site: one page per file, sections under their headings.

Use it for documentation that lives next to the code (README files, API notes). Each page's URL is the file's
location under --base-url (for example its GitHub link), so a citation is a link you can click.
"""

from __future__ import annotations

import os
import re

from .crawl import Page

_SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", "dist", "build", ".terraform"}
_MAX_BYTES = 200_000
_HEADING = re.compile(r"^(#{1,4})\s+(.*?)\s*#*\s*$")
_FENCE = re.compile(r"^\s*(```|~~~)")


def parse_markdown(url: str, text: str, fallback_title: str) -> Page:
    """Split one Markdown document into (heading, text) sections.

    Paragraphs, lists, tables and fenced code blocks each become one section; their line breaks are kept so a curl
    example or a table still reads correctly.
    """
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    title = ""
    heading = fallback_title
    sections: list[tuple[str, str]] = []
    block: list[str] = []
    in_fence = False

    def flush() -> None:
        body = "\n".join(block).strip()
        if body:
            sections.append((heading, body))
        block.clear()

    for line in text.splitlines():
        if _FENCE.match(line):
            if not in_fence:
                flush()
            block.append(line.rstrip())
            if in_fence:
                flush()
            in_fence = not in_fence
            continue
        if in_fence:
            block.append(line.rstrip())
            continue
        match = _HEADING.match(line)
        if match:
            flush()
            heading = match.group(2).strip()
            if not title and len(match.group(1)) == 1:
                title = heading
            continue
        if not line.strip():
            flush()
            continue
        block.append(line.rstrip())
    flush()
    return Page(url=url, title=title or fallback_title, sections=sections)


def load_docs(directory: str, base_url: str) -> list[Page]:
    """Every .md file under directory, as pages whose URLs are base_url + the file's relative path."""
    pages: list[Page] = []
    for root, dirs, files in os.walk(directory):
        dirs[:] = sorted(d for d in dirs if d not in _SKIP_DIRS and not d.startswith("."))
        for name in sorted(files):
            path = os.path.join(root, name)
            if not name.lower().endswith(".md") or os.path.getsize(path) > _MAX_BYTES:
                continue
            rel = os.path.relpath(path, directory).replace(os.sep, "/")
            with open(path, encoding="utf-8", errors="replace") as f:
                page = parse_markdown(f"{base_url.rstrip('/')}/{rel}", f.read(), rel)
            if page.sections:
                pages.append(page)
    return pages

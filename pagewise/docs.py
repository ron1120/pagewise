"""Read a project folder as if it were a site, so the project can answer questions about itself.

Markdown files become one page each, with sections under their headings. With include_code=True the code and
config files are read too, in windows of about 30 lines, each window a page of its own. Every page's URL is the
file's location under --base-url (for a code window, with a #L10-L40 line anchor), so a citation is a link
you can click.

Only an allowlist of file types is read, and anything that looks like a secret is skipped by name.
"""

from __future__ import annotations

import os
import re

from .crawl import Page

_SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", "dist", "build", ".terraform", "alembic_cache"}
_ALLOWED_HIDDEN_DIRS = {".github"}
_MAX_BYTES = 200_000

_CODE_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".yml", ".yaml", ".tf", ".sh", ".ini", ".toml", ".cfg", ".conf",
    ".css", ".html", ".sql", ".json", ".mako",
}
_CODE_NAMES = {"dockerfile", "makefile"}
# Never read these, whatever their extension: keys, certificates, Terraform state and real variable files.
_SECRET_MARKERS = (".pem", ".key", ".crt", ".p12", ".tfstate", "id_rsa", "id_ed25519", ".tfvars", "credentials")
_LOCKFILES = {"package-lock.json", "yarn.lock", "poetry.lock", "pnpm-lock.yaml"}
_WINDOW_LINES = 30
_WINDOW_CHARS = 1000
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
    return load_repo(directory, base_url, include_code=False)


def _is_secret(name: str) -> bool:
    lower = name.lower()
    if lower.endswith(".example") or ".example." in lower:
        return False  # a template with placeholder values, safe to read
    return lower.startswith(".env") or any(marker in lower for marker in _SECRET_MARKERS)


def _is_code(name: str) -> bool:
    lower = name.lower()
    ext = os.path.splitext(lower)[1]
    return (
        lower in _CODE_NAMES
        or ext in _CODE_EXTENSIONS
        or lower.endswith(".example")
        or lower.startswith("dockerfile")
    ) and lower not in _LOCKFILES


def code_windows(url: str, rel: str, text: str) -> list[Page]:
    """Split a code or config file into windows of about 30 lines, one page per window."""
    lines = text.splitlines()
    pages: list[Page] = []
    start = 0
    size = 0
    for i, line in enumerate(lines):
        size += len(line) + 1
        last = i == len(lines) - 1
        full = (i - start + 1) >= _WINDOW_LINES or size >= _WINDOW_CHARS
        blank_break = not line.strip() and (i - start + 1) >= 12
        if full or blank_break or last:
            body = "\n".join(lines[start : i + 1]).strip("\n")
            if body.strip():
                a, b = start + 1, i + 1
                pages.append(Page(f"{url}#L{a}-L{b}", rel, [(f"lines {a}-{b}", body)]))
            start, size = i + 1, 0
    return pages


def load_repo(directory: str, base_url: str, include_code: bool = False) -> list[Page]:
    """Markdown pages, plus (with include_code) the project's code and config files in line windows."""
    pages: list[Page] = []
    for root, dirs, files in os.walk(directory):
        dirs[:] = sorted(
            d for d in dirs if d not in _SKIP_DIRS and (not d.startswith(".") or d in _ALLOWED_HIDDEN_DIRS)
        )
        for name in sorted(files):
            path = os.path.join(root, name)
            if name.startswith(".") and name.lower() != ".dockerignore" or _is_secret(name):
                continue
            is_markdown = name.lower().endswith(".md")
            if not (is_markdown or (include_code and _is_code(name))) or os.path.getsize(path) > _MAX_BYTES:
                continue
            rel = os.path.relpath(path, directory).replace(os.sep, "/")
            url = f"{base_url.rstrip('/')}/{rel}"
            with open(path, encoding="utf-8", errors="replace") as f:
                text = f.read()
            if is_markdown:
                page = parse_markdown(url, text, rel)
                if page.sections:
                    pages.append(page)
            else:
                pages.extend(code_windows(url, rel, text))
    return pages

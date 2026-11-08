"""Crawl a website and turn each page into titled sections of plain text.

Polite by default: it honours robots.txt, stays on one host, identifies itself and waits between requests.
"""

from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET
from collections import deque
from dataclasses import dataclass, field
from typing import Callable
from urllib import robotparser
from urllib.parse import urldefrag, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from .config import USER_AGENT

# fetch(url) -> (status_code, content_type, body). Injectable so tests never touch the network.
Fetch = Callable[[str], tuple[int, str, str]]

_SKIP_TAGS = ["script", "style", "noscript", "svg", "nav", "header", "footer", "form", "template"]
_TEXT_TAGS = ["h1", "h2", "h3", "h4", "p", "li", "pre", "blockquote", "figcaption", "td", "th"]
_LEAF_TAGS = {"p", "li", "pre", "blockquote", "figcaption", "td", "th"}
_SKIP_EXT = re.compile(r"\.(png|jpe?g|gif|svg|webp|ico|pdf|zip|css|js|json|xml|txt|mp4|woff2?)$", re.I)


@dataclass
class Page:
    url: str
    title: str
    sections: list[tuple[str, str]] = field(default_factory=list)  # (heading, text)

    def to_dict(self) -> dict:
        return {"url": self.url, "title": self.title, "sections": [list(s) for s in self.sections]}

    @classmethod
    def from_dict(cls, d: dict) -> "Page":
        return cls(d["url"], d["title"], [(h, t) for h, t in d["sections"]])


def default_fetch(url: str) -> tuple[int, str, str]:
    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=15)
    return response.status_code, response.headers.get("content-type", ""), response.text


def normalize(url: str) -> str:
    """One canonical form per page: no fragment, no query, and a bare host gets a trailing slash."""
    url, _ = urldefrag(url)
    parts = urlparse(url)
    return f"{parts.scheme}://{parts.netloc}{parts.path or '/'}"


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _text(el) -> str:
    """The visible text of an element.

    Animated headings wrap every word, or every letter, in its own <span>. Letters must be glued back together,
    words need a space between them, so: if every piece of text is a single character, join with nothing.
    """
    pieces = list(el.strings)
    glyphs = [p.strip() for p in pieces if p.strip()]
    letters = bool(glyphs) and all(len(g) == 1 for g in glyphs) and len(glyphs) > 3
    return _clean(("" if letters else " ").join(pieces))


def extract(url: str, html: str) -> Page:
    """Pull the readable content out of one HTML page, grouped under its headings."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(_SKIP_TAGS):
        tag.decompose()
    # Anything marked aria-hidden is decoration (icon sprites, the duplicated half of a scrolling list).
    for tag in soup.find_all(attrs={"aria-hidden": "true"}):
        if not tag.decomposed:
            tag.decompose()
    title = _text(soup.title) if soup.title else ""
    root = soup.find("main") or soup.find("article") or soup.body or soup
    if not title:
        h1 = root.find("h1")
        title = _text(h1) if h1 else url

    sections: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    heading = title
    for el in root.find_all(_TEXT_TAGS):
        # A <p> or <h3> inside an <li> is already part of the <li>'s text: don't count it twice, and don't let a
        # card's own title become the heading of the card that follows it.
        if any(p.name in _LEAF_TAGS for p in el.parents):
            continue
        text = _text(el)
        if not text or (el.name in _LEAF_TAGS and (heading, text) in seen):
            continue
        seen.add((heading, text))
        if el.name.startswith("h"):
            heading = text
            continue
        sections.append((heading, text))
    return Page(url=url, title=title, sections=sections)


def _links(base: str, html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith(("mailto:", "tel:", "javascript:")):
            continue
        out.append(normalize(urljoin(base, href)))
    return out


def _sitemap_urls(origin: str, fetch: Fetch) -> list[str]:
    try:
        status, _, body = fetch(origin + "/sitemap.xml")
        if status != 200:
            return []
        return [normalize(el.text.strip()) for el in ET.fromstring(body).iter() if el.tag.endswith("loc") and el.text]
    except Exception:
        return []


def _robots(origin: str) -> robotparser.RobotFileParser | None:
    try:
        response = requests.get(origin + "/robots.txt", headers={"User-Agent": USER_AGENT}, timeout=10)
        if response.status_code != 200:
            return None
        rp = robotparser.RobotFileParser()
        rp.parse(response.text.splitlines())
        return rp
    except requests.RequestException:
        return None


def crawl(
    start_url: str,
    max_pages: int = 60,
    delay: float = 0.3,
    fetch: Fetch = default_fetch,
    respect_robots: bool = True,
) -> list[Page]:
    """Breadth-first crawl of one host, starting at start_url (and its sitemap, if it has one)."""
    start = normalize(start_url)
    parsed = urlparse(start)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    robots = _robots(origin) if respect_robots and fetch is default_fetch else None

    queue: deque[str] = deque([start, *_sitemap_urls(origin, fetch)])
    seen: set[str] = set()
    pages: list[Page] = []

    while queue and len(pages) < max_pages:
        url = queue.popleft()
        if url in seen or urlparse(url).netloc != parsed.netloc or _SKIP_EXT.search(urlparse(url).path):
            continue
        seen.add(url)
        if robots is not None and not robots.can_fetch(USER_AGENT, url):
            continue
        try:
            status, content_type, body = fetch(url)
        except requests.RequestException:
            continue
        if status != 200 or "html" not in content_type.lower():
            continue
        page = extract(url, body)
        if page.sections:
            pages.append(page)
        queue.extend(link for link in _links(url, body) if link not in seen)
        time.sleep(delay if fetch is default_fetch else 0)
    return pages

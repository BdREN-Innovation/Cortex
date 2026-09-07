"""HTML -> title, prose text, breadcrumb and outbound links."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from bs4 import BeautifulSoup

# Elements that are never page content.
STRIP_TAGS = ["script", "style", "noscript", "template", "svg", "iframe", "form"]
# Elements that are usually chrome. Removed only when the page has a <main>
# or <article> to fall back on, so we never blank out a simple page.
CHROME_TAGS = ["nav", "header", "footer", "aside"]

MAIN_SELECTORS = ["main", "article", "[role=main]", "#content", ".content", "#main"]


@dataclass
class Extracted:
    title: str
    text: str
    section_path: list[str] = field(default_factory=list)
    links: list[str] = field(default_factory=list)
    canonical_url: str = ""
    lang: str = "en"
    meta: dict = field(default_factory=dict)


def _collapse(text: str) -> str:
    text = re.sub(r"[ \t\xa0]+", " ", text)
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
    return "\n".join(line.strip() for line in text.splitlines()).strip()


def extract(html: str, url: str) -> Extracted:
    soup = BeautifulSoup(html, "lxml")

    links = [a.get("href") for a in soup.find_all("a", href=True)]
    links = [href for href in links if href and not href.startswith(("mailto:", "tel:", "javascript:"))]

    canonical = ""
    tag = soup.find("link", rel=lambda v: v and "canonical" in v)
    if tag and tag.get("href"):
        canonical = tag["href"].strip()

    lang = (soup.html.get("lang") if soup.html else None) or "en"

    meta = {}
    for name in ("description", "author", "keywords"):
        node = soup.find("meta", attrs={"name": name})
        if node and node.get("content"):
            meta[name] = node["content"].strip()
    published = soup.find("meta", attrs={"property": "article:published_time"})
    if published and published.get("content"):
        meta["published_at"] = published["content"].strip()

    title = ""
    if soup.title and soup.title.string:
        title = soup.title.string.strip()
    h1 = soup.find("h1")
    if h1 and h1.get_text(strip=True):
        title = title or h1.get_text(strip=True)

    section_path = _breadcrumb(soup) or _heading_path(soup, title)

    for tag_name in STRIP_TAGS:
        for node in soup.find_all(tag_name):
            node.decompose()

    body = None
    for selector in MAIN_SELECTORS:
        body = soup.select_one(selector)
        if body is not None:
            break
    if body is None:
        for tag_name in CHROME_TAGS:
            for node in soup.find_all(tag_name):
                node.decompose()
        body = soup.body or soup

    text = _collapse(body.get_text("\n"))

    return Extracted(
        title=title,
        text=text,
        section_path=section_path,
        links=links,
        canonical_url=canonical,
        lang=lang,
        meta=meta,
    )


def _breadcrumb(soup: BeautifulSoup) -> list[str]:
    node = soup.find(attrs={"class": re.compile("breadcrumb", re.I)}) or soup.find(
        attrs={"aria-label": re.compile("breadcrumb", re.I)}
    )
    if not node:
        return []
    parts = [a.get_text(strip=True) for a in node.find_all(["a", "li", "span"])]
    seen, out = set(), []
    for part in parts:
        if part and part not in seen:
            seen.add(part)
            out.append(part)
    return out[:6]


def _heading_path(soup: BeautifulSoup, title: str) -> list[str]:
    """Fallback breadcrumb: the page's own heading hierarchy."""
    path = []
    for level in ("h1", "h2"):
        node = soup.find(level)
        if node:
            text = node.get_text(strip=True)
            if text and text not in path:
                path.append(text)
    if not path and title:
        path = [title]
    return path

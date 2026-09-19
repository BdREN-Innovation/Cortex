"""What else is on this page: links and linked files.

This module performs structural HTML discovery only.
TEAM A OWNS THIS FILE.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

# Linked files worth pulling down.
DOCUMENT_EXTENSIONS = (
    ".pdf",
    ".docx",
    ".doc",
    ".xlsx",
    ".xls",
    ".pptx",
    ".csv",
)


@dataclass
class Discovered:
    """Everything structural one page tells us. No prose, by design."""

    links: list[str] = field(default_factory=list)
    document_links: list[str] = field(default_factory=list)
    canonical_url: str = ""
    lang: str = "en"


def _is_document_url(url: str) -> bool:
    """Return True when the URL points to a supported document type."""
    path = urlsplit(url).path.lower()
    return path.endswith(DOCUMENT_EXTENSIONS)


def discover(html: str, url: str) -> Discovered:
    """Read a page for links, documents, canonical URL and language.

    This function does not extract page text.
    """
    soup = BeautifulSoup(html, "html.parser")

    links: list[str] = []
    document_links: list[str] = []

    seen_links: set[str] = set()
    seen_documents: set[str] = set()

    for anchor in soup.find_all("a", href=True):
        href = anchor.get("href")

        if not isinstance(href, str):
            continue

        href = href.strip()

        if not href:
            continue

        # Ignore links that cannot lead to crawlable web resources.
        lowered = href.lower()

        if (
            lowered.startswith("mailto:")
            or lowered.startswith("tel:")
            or lowered.startswith("javascript:")
        ):
            continue

        absolute_url = urljoin(url, href)

        # Only HTTP(S) URLs should enter the crawler.
        scheme = urlsplit(absolute_url).scheme.lower()

        if scheme not in {"http", "https"}:
            continue

        if _is_document_url(absolute_url):
            if absolute_url not in seen_documents:
                seen_documents.add(absolute_url)
                document_links.append(absolute_url)
        else:
            # Keep normal links exactly as they appeared in the HTML.
            if href not in seen_links:
                seen_links.add(href)
                links.append(href)

    # Find <link rel="canonical" href="...">
    canonical_url = ""

    canonical_tag = soup.find(
        "link",
        rel=lambda value: (
            value
            and (
                "canonical" in value
                if isinstance(value, str)
                else "canonical" in value
            )
        ),
    )

    if canonical_tag:
        href = canonical_tag.get("href")

        if isinstance(href, str) and href.strip():
            canonical_url = urljoin(url, href.strip())

    # Read language from <html lang="...">.
    lang = "en"

    html_tag = soup.find("html")

    if html_tag:
        html_lang = html_tag.get("lang")

        if isinstance(html_lang, str) and html_lang.strip():
            lang = html_lang.strip()

    return Discovered(
        links=links,
        document_links=document_links,
        canonical_url=canonical_url,
        lang=lang,
    )